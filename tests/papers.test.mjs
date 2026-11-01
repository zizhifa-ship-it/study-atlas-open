import assert from 'node:assert/strict';
import test from 'node:test';
import {libraryMarkdown, paperBibtex, paperRis, papersCsv, researchMarkdown} from '../exports.js';

function paper(overrides={}) {
  return {
    id:'p1', title:'Local Learning', authors:['Ada Lovelace'], year:2024,
    venue:'Journal of Tests', doi:'10.1234/test', arxivId:'', url:'https://example.org/paper', pdfUrl:'',
    abstract:'An abstract.', keywords:['learning'], tags:[], categoryId:'net', stage:'included', readState:'read',
    review:{question:'How?', method:'Experiment', data:'N=10', findings:'A finding', limitations:'A limit', relevance:'Useful'},
    notes:[], ...overrides,
  };
}
const library = {categories:[{id:'net',name:'研究',parentId:null}], videos:[], insights:[], papers:[paper()],
  research:{question:'How do local tools help?', scope:'Local', searchStrategy:'Crossref', inclusion:'Peer reviewed', exclusion:'No abstract', synthesis:'They help.', updatedAt:'2026-11-01'}};

test('BibTeX exports authors, title, venue, DOI and stable unique keys', () => {
  const output = paperBibtex([paper(), paper({title:'Second Paper', authors:['Alan Turing']})]);
  assert.match(output, /@article\{/);
  assert.match(output, /Ada Lovelace/);
  assert.match(output, /Local Learning/);
  assert.match(output, /10\.1234\/test/);
  const keys = [...output.matchAll(/@article\{([^,]+),/g)].map(match => match[1]);
  assert.equal(keys.length, 2);
  assert.equal(new Set(keys).size, 2);
});

test('RIS and CSV preserve matrix fields', () => {
  const ris = paperRis([paper()]);
  assert.match(ris, /TY  - JOUR/);
  assert.match(ris, /TI  - Local Learning/);
  assert.match(ris, /DO  - 10\.1234\/test/);
  const csv = papersCsv([paper()]);
  assert.match(csv, /^title,authors,year,venue,doi,/);
  assert.match(csv, /"Local Learning"/);
  assert.match(csv, /"A finding"/);
});

test('research Markdown contains question, included matrix and references', () => {
  const output = researchMarkdown(library);
  assert.match(output, /## 研究问题/);
  assert.match(output, /How do local tools help\?/);
  assert.match(output, /## 综述矩阵/);
  assert.match(output, /Local Learning/);
  assert.match(output, /## 综合论证/);
});

test('library Markdown includes papers and research path', () => {
  const output = libraryMarkdown(library);
  assert.match(output, /## 论文知识库/);
  assert.match(output, /Local Learning/);
  assert.match(output, /## 学术路径/);
  assert.match(output, /How do local tools help\?/);
  assert.doesNotMatch(output, /apiKey|client_secret/);
});
