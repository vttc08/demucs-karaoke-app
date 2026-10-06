"""Small ASGI middleware for bounded queue-creation request bodies."""

MAX_QUEUE_REQUEST_BODY_BYTES = 512 * 1024


class QueueRequestBodyLimitMiddleware:
    def __init__(
        self, app, *, queue_path: str, max_bytes: int = MAX_QUEUE_REQUEST_BODY_BYTES
    ):
        self.app = app
        self.queue_path = queue_path.rstrip("/")
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"].rstrip("/") != self.queue_path
        ):
            await self.app(scope, receive, send)
            return

        content_length = next(
            (
                value
                for key, value in scope["headers"]
                if key.lower() == b"content-length"
            ),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > self.max_bytes:
                    await self._reject(send)
                    return
            except ValueError:
                pass

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_bytes:
                await self._reject(send)
                return
            if not message.get("more_body", False):
                break

        body_bytes = bytes(body)
        delivered = False

        async def replay_body():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {
                    "type": "http.request",
                    "body": body_bytes,
                    "more_body": False,
                }
            return await receive()

        await self.app(scope, replay_body, send)

    @staticmethod
    async def _reject(send):
        body = b'{"detail":"Queue request body too large"}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
