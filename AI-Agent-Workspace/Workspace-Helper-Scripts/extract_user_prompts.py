from pathlib import Path

FILE = Path("AI-Agent-Workspace/ChatHistory/2025-10-21.md")

def main() -> None:
    lines = FILE.read_text(encoding="utf-8").splitlines()
    prompts = []
    for idx, line in enumerate(lines):
        if line.startswith("jfjordanfarr:"):
            snippet = "\n".join(lines[idx: min(idx + 12, len(lines))])
            prompts.append(snippet)
    print(f"total prompts: {len(prompts)}\n")
    print("\n\n".join(prompts))

if __name__ == "__main__":
    main()
