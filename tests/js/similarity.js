function findLongestMatch(a, b, alo, ahi, blo, bhi, b2j) {
  let besti = alo, bestj = blo, bestsize = 0;
  let j2len = {};
  for (let i = alo; i < ahi; i++) {
    const newj2len = {};
    const indices = b2j[a[i]] || [];
    for (const j of indices) {
      if (j < blo) continue;
      if (j >= bhi) break;
      const k = (j2len[j - 1] || 0) + 1;
      newj2len[j] = k;
      if (k > bestsize) {
        besti = i - k + 1;
        bestj = j - k + 1;
        bestsize = k;
      }
    }
    j2len = newj2len;
  }
  return [besti, bestj, bestsize];
}

function getMatchingBlocks(a, b) {
  const b2j = {};
  for (let j = 0; j < b.length; j++) {
    const c = b[j];
    (b2j[c] = b2j[c] || []).push(j);
  }
  const queue = [[0, a.length, 0, b.length]];
  const matchingBlocks = [];
  while (queue.length) {
    const [alo, ahi, blo, bhi] = queue.pop();
    const [i, j, k] = findLongestMatch(a, b, alo, ahi, blo, bhi, b2j);
    if (k) {
      matchingBlocks.push([i, j, k]);
      if (alo < i && blo < j) queue.push([alo, i, blo, j]);
      if (i + k < ahi && j + k < bhi) queue.push([i + k, ahi, j + k, bhi]);
    }
  }
  return matchingBlocks;
}

function sequenceMatcherRatio(a, b) {
  const blocks = getMatchingBlocks(a, b);
  let matches = 0;
  for (const block of blocks) matches += block[2];
  const total = a.length + b.length;
  return total === 0 ? 1.0 : (2.0 * matches) / total;
}

module.exports = { sequenceMatcherRatio };
