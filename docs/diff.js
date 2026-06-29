const sentenceElement = document.getElementById('sentence');
const resultElement = document.getElementById('result');
const sentences = document.getElementById('sentences');
const undoButton = document.getElementById('undo');
async function loadJsonPatch() {
    const jsonpatch = await import('https://esm.sh/fast-json-patch@3.1.1');
    return jsonpatch;
}

loadJsonPatch().then(jsonpatch => {
    window.jsonpatch = jsonpatch;
    console.log("jsonpatch loaded:", jsonpatch);
});



let exampleJSON = JSON.parse(`
[{"start":1.56,"end":12.481,"text":"Said, I'm the shit, they can't fuck with me if they wanted to","words":[{"word":"Said,","start":1.56,"end":3.08,"score":0.531},{"word":"I'm","start":3.6,"end":3.98,"score":0.54},{"word":"the","start":5.521,"end":5.961,"score":0.603},{"word":"shit,","start":6.021,"end":6.321,"score":0.703},{"word":"they","start":7.241,"end":7.401,"score":0.426},{"word":"can't","start":7.461,"end":7.681,"score":0.37},{"word":"fuck","start":7.701,"end":7.921,"score":0.195},{"word":"with","start":7.981,"end":9.281,"score":0.826},{"word":"me","start":9.381,"end":9.541,"score":0.744},{"word":"if","start":9.961,"end":10.041,"score":0.371},{"word":"they","start":10.101,"end":10.281,"score":0.578},{"word":"wanted","start":10.361,"end":10.761,"score":0.642},{"word":"to","start":11.561,"end":12.481,"score":0.506}]},{"start":12.821,"end":13.721,"text":"God damn","words":[{"word":"God","start":12.821,"end":13.001,"score":0.48},{"word":"damn","start":13.261,"end":13.721,"score":0.61}]},{"start":14.761,"end":19.002,"text":"Said, Lil bitch, you can't fuck with me if you wanted to","words":[{"word":"Said,","start":14.761,"end":15.122,"score":0.442},{"word":"Lil","start":15.162,"end":15.482,"score":0.784},{"word":"bitch,","start":15.622,"end":15.882,"score":0.405},{"word":"you","start":16.102,"end":16.282,"score":0.941},{"word":"can't","start":16.342,"end":16.542,"score":0.65},{"word":"fuck","start":16.602,"end":16.802,"score":0.654},{"word":"with","start":16.842,"end":17.042,"score":0.368},{"word":"me","start":17.102,"end":17.262,"score":0.886},{"word":"if","start":17.642,"end":17.742,"score":0.718},{"word":"you","start":17.782,"end":18.002,"score":0.93},{"word":"wanted","start":18.042,"end":18.522,"score":0.649},{"word":"to","start":18.562,"end":19.002,"score":0.816}]}]
`)


function renderSentences(JSONContent){
    let sentenceText = JSONContent.map(segment => segment.text);
    sentences.innerHTML = '';
    for (const [idx,sentence] of sentenceText.entries()) {
        // render to DOM
        sentences.innerHTML += sentence.split(' ').map((word, wordIdx) => `<span data-word-index="${wordIdx}" data-idx="${idx}" onclick="handleWordClick(this)">${word}</span>`).join(' ') + `<br />`;
        sentences.innerHTML += `<button onclick="mergeSentences(${idx})" class="mergeBelow" data-index="${idx}">Merge Below</button><br />`;
    }
}

renderSentences(exampleJSON);

function handleWordClick(element) {
    const wordIndex = element.getAttribute('data-word-index');
    const idx = element.getAttribute('data-idx');
    console.log(`Clicked word index: ${wordIndex} in sentence index: ${idx}`);
    resultElement.textContent = `Clicked word index: ${wordIndex}`;
    let oldJSON = exampleJSON;
    exampleJSON = split(exampleJSON, parseInt(idx), parseInt(wordIndex));
    const patch = jsonpatch.compare(oldJSON, exampleJSON);
    undoPatch = patch.map(op => {
        const oldValue = jsonpatch.getValueByPointer(oldJSON, op.path);
        if (op.op === 'replace') {
            return { op: 'replace', path: op.path, value: oldValue };
        }
        if (op.op === 'add') {
            return { op: 'remove', path: op.path };
        }
            if (op.op === 'remove') {
    return { op: 'add', path: op.path, value: oldValue };
    }
    return op;
}).reverse();
    renderSentences(exampleJSON);
}   

function mergeSentences(index) {
    let oldJSON = exampleJSON;
    exampleJSON = merge(exampleJSON, index);
    const patch = jsonpatch.compare(oldJSON, exampleJSON);
    undoPatch = patch.map(op => {
    const oldValue = jsonpatch.getValueByPointer(oldJSON, op.path);

    if (op.op === 'replace') {
    return { op: 'replace', path: op.path, value: oldValue };
    }
    if (op.op === 'add') {
    return { op: 'remove', path: op.path };
    }
    if (op.op === 'remove') {
    return { op: 'add', path: op.path, value: oldValue };
    }
    return op;
}).reverse();

    console.log(patch);
    renderSentences(exampleJSON);
}

let undoPatch = [];

function undoLastChange() {
    if (undoPatch.length > 0) {
        exampleJSON = jsonpatch.applyPatch(exampleJSON, undoPatch).newDocument;
        renderSentences(exampleJSON);
        console.log("Undo applied. Current state:", exampleJSON);
    }
}
if (undoButton) {
    undoButton.addEventListener('click', () => {
        undoLastChange();
    });
}
