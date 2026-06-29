function merge(object, index) {
    if (index < 0 || index >= object.length - 1) { throw new Error("Index out of range for merging segments."); }
    mergedSegment = {
        start: object[index].start,
        end: object[index + 1].end,
        text: object[index].text + " " + object[index + 1].text,
        words: object[index].words.concat(object[index + 1].words)
    };
    return object.slice(0, index).concat([mergedSegment], object.slice(index + 2));
}

example_segments = [
    {start: 0, end: 1, text: "Hello", words: [{word: "Hello", start: 0, end: 1}]},
    {start: 1, end: 2, text: "World", words: [{word: "World", start: 1, end: 2}]},
    {start: 2, end: 3, text: "!", words: [{word: "!", start: 2, end: 3}]}
];
merged = merge(example_segments, 0);
console.log(merged);

function splitSegment(object, index) { // segment, wordIndex
    if (index < 0 || index >= object.length) { return [object]; } // No split if index is out of range
    const segmentsToSplit = object.words;
    const firstPart = segmentsToSplit.slice(0, index);
    const secondPart = segmentsToSplit.slice(index);
    const firstSegment = {
        start: object.start,
        end: firstPart[firstPart.length - 1].end,
        text: firstPart.map(w => w.word).join(" "),
        words: firstPart
    };
    const secondSegment = {
        start: secondPart[0].start,
        end: object.end,
        text: secondPart.map(w => w.word).join(" "),
        words: secondPart
    };
    return [firstSegment, secondSegment];
}

function split(object, index, wordIndex) {
    if (index < 0 || index >= object.length) { throw new Error("Index out of range for splitting segments."); }
    return [
        ...object.slice(0, index),
        ...splitSegment(object[index], wordIndex),
        ...object.slice(index + 1)
    ]
}

example_segments = [
    {start: 0, end: 5, text: "Hello world one two three.", words: [
        {word: "Hello", start: 0, end: 1},
        {word: "world", start: 1, end: 2},
        {word: "one", start: 2, end: 3},
        {word: "two", start: 3, end: 4},
        {word: "three.", start: 4, end: 5}
    ]},
    {start: 5, end: 6, text: "World", words: [{word: "World", start: 1, end: 2}]},
    {start: 6, end: 7, text: "!", words: [{word: "!", start: 2, end: 3}]}
];


console.log(split(example_segments, 0, 2)); // Split the first segment at word index 1