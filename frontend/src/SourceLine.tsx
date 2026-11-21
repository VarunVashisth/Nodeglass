// Presentation-only token coloring; all analysis uses the backend syntax trees.
const tokens =
  /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\/\/.*|#.*|\b(?:def|class|return|if|else|elif|for|while|try|except|finally|async|await|yield|import|from|as|in|is|not|and|or|True|False|None|function|const|let|var|new|export|default|extends|throw|catch|true|false|null|undefined)\b|\b\d+(?:\.\d+)?\b)/g;
export default function SourceLine({ line }: { line: string }) {
  return (
    <>
      {line.split(tokens).map((token, index) => {
        const kind = /^["']/.test(token)
          ? "string"
          : /^(#|\/\/)/.test(token)
            ? "comment"
            : /^\d/.test(token)
              ? "number"
              : /^[a-zA-Z]+$/.test(token) && tokens.test(token)
                ? "keyword"
                : "";
        tokens.lastIndex = 0;
        return (
          <span className={kind ? "syntax-" + kind : undefined} key={index}>
            {token}
          </span>
        );
      })}
    </>
  );
}
