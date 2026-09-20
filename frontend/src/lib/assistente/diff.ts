/**
 * A diferença entre dois textos, linha a linha — o que o Histórico mostra ao
 * lado de uma versão: o que ela tem a mais e a menos do que a que está no ar.
 *
 * É um LCS de linhas, sem dependência nova: os textos têm no máximo alguns
 * milhares de caracteres (o limite do banco), então a tabela cabe com folga.
 * Linha é a unidade porque é como um prompt se escreve e se revisa — uma
 * instrução por linha —, e um diff de caracteres num parágrafo reescrito vira
 * confete.
 */

export type DiffLine = {
  kind: "same" | "added" | "removed";
  text: string;
};

function lines(text: string): string[] {
  return text === "" ? [] : text.split("\n");
}

/**
 * `before` é a referência (a versão no ar); `after` é a versão olhada. Uma
 * linha `added` está em `after` e não em `before`; `removed`, o contrário.
 */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = lines(before);
  const b = lines(after);
  const n = a.length;
  const m = b.length;

  // lcs[i][j] = comprimento da subsequência comum de a[i..] e b[j..].
  const lcs: number[][] = Array.from({ length: n + 1 }, () =>
    new Array<number>(m + 1).fill(0),
  );

  for (let i = n - 1; i >= 0; i -= 1) {
    for (let j = m - 1; j >= 0; j -= 1) {
      lcs[i][j] =
        a[i] === b[j]
          ? lcs[i + 1][j + 1] + 1
          : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
    }
  }

  const result: DiffLine[] = [];
  let i = 0;
  let j = 0;

  while (i < n && j < m) {
    if (a[i] === b[j]) {
      result.push({ kind: "same", text: a[i] });
      i += 1;
      j += 1;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      result.push({ kind: "removed", text: a[i] });
      i += 1;
    } else {
      result.push({ kind: "added", text: b[j] });
      j += 1;
    }
  }

  for (; i < n; i += 1) {
    result.push({ kind: "removed", text: a[i] });
  }

  for (; j < m; j += 1) {
    result.push({ kind: "added", text: b[j] });
  }

  return result;
}
