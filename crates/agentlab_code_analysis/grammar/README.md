# AgentLab ArkTS grammar extension

The inherited grammar/scanner and MIT license are retained under upstream/.
PROVENANCE.json identifies exact upstream and generation tool versions.
grammar.js adds nonempty leading-dot style blocks as pair values, fixing the
pinned code-workshop stateStyles case. Ordinary object syntax stays inherited.

Generated C and node types are committed so Rust users need no Node runtime.
Regenerate with tools installed outside the analyzed Workspace:

```sh
mkdir -p "$PARSER_TOOLS"
cp package.json package-lock.json "$PARSER_TOOLS/"
npm ci --prefix "$PARSER_TOOLS" --no-audit --no-fund
NODE_PATH="$PARSER_TOOLS/node_modules" "$PARSER_TOOLS/node_modules/.bin/tree-sitter" generate
```

Run from this grammar directory. The Rust regression compares unchanged upstream
parsing against the extension, checks normal objects and retains malformed syntax.
The generated parser is about24 MB of source, not a binary Workspace snapshot.
