use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use tree_sitter::{Node, Parser};
extern "C" {
    fn tree_sitter_agentlab_arkts() -> *const ();
}
const LANGUAGE: tree_sitter_language::LanguageFn =
    unsafe { tree_sitter_language::LanguageFn::from_raw(tree_sitter_agentlab_arkts) };
pub const GRAMMAR: &str = "agentlab-arkts@0.1.0 (tree-sitter-arkts@0.2.0 + stateStyles)";
pub const GRAMMAR_DIGEST: &str = env!("AGENTLAB_GRAMMAR_DIGEST");

pub fn digest(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}
fn text<'a>(node: Node, source: &'a [u8]) -> &'a str {
    std::str::from_utf8(&source[node.byte_range()]).unwrap_or("")
}
fn field(node: Node, name: &str, source: &[u8]) -> String {
    node.child_by_field_name(name)
        .map(|n| text(n, source).to_owned())
        .unwrap_or_default()
}
fn span(node: Node) -> Value {
    json!({"startByte":node.start_byte(),"endByte":node.end_byte(),
        "startLine":node.start_position().row+1,"endLine":node.end_position().row+1,
        "startColumnByte":node.start_position().column,"endColumnByte":node.end_position().column})
}
pub struct Analysis {
    pub rows: Vec<Value>,
    pub has_errors: bool,
}
struct Collector<'a> {
    source: &'a [u8],
    path: &'a str,
    revision: &'a str,
    rows: Vec<Value>,
    occurrences: BTreeMap<String, usize>,
}
impl Collector<'_> {
    fn emit(&mut self, node: Node, kind: &str, anchor: &str, extra: Value) -> String {
        let key = format!("{}\0{}\0{}", self.path, kind, anchor);
        let ordinal = self.occurrences.entry(key.clone()).or_default();
        let id = format!(
            "ast-{}",
            &digest(format!("{}\0{}", key, ordinal).as_bytes())[..24]
        );
        *ordinal += 1;
        let mut row = json!({"id":id,"kind":kind,"path":self.path,
            "sourceRevision":self.revision,"syntaxKind":node.kind(),"span":span(node),
            "method":GRAMMAR,"syntaxHasErrors":node.has_error()});
        row.as_object_mut()
            .unwrap()
            .extend(extra.as_object().unwrap().clone());
        self.rows.push(row);
        id
    }
    fn visit(&mut self, node: Node, owner: &str) {
        let mut scope = owner.to_owned();
        if node.is_error() || node.is_missing() {
            self.emit(
                node,
                "parse-error",
                node.kind(),
                json!({"missing":node.is_missing(),"sourceText":text(node,self.source)}),
            );
        }
        match node.kind() {
            "import_statement" | "export_statement" => {
                if let Some(source) = node.child_by_field_name("source") {
                    let literal = text(source, self.source);
                    let specifier = literal
                        .get(1..literal.len().saturating_sub(1))
                        .unwrap_or("");
                    self.emit(node,"module-reference",specifier,json!({"specifier":specifier,
                        "statement":text(node,self.source),"resolution":"unresolved",
                        "referenceType":if node.kind()=="import_statement" {"import"} else {"export"}}));
                }
            }
            "class_declaration"
            | "abstract_class_declaration"
            | "struct_declaration"
            | "function_declaration"
            | "method_definition"
            | "interface_declaration"
            | "enum_declaration"
            | "type_alias_declaration" => {
                let name = field(node, "name", self.source);
                scope = if owner.is_empty() {
                    name.clone()
                } else {
                    format!("{owner}::{name}")
                };
                self.emit(
                    node,
                    "symbol",
                    &scope,
                    json!({"symbol":name,"qualifiedName":scope,"owner":owner}),
                );
            }
            "call_expression" => {
                let target = field(node, "function", self.source);
                self.emit(node,"call",&format!("{owner}::{target}"),json!({"targetExpression":target,"owner":owner,"resolution":"syntactic-unresolved"}));
            }
            "decorator" => {
                let expression = text(node, self.source);
                self.emit(
                    node,
                    "decorator",
                    &format!("{owner}::{expression}"),
                    json!({"expression":expression,"owner":owner}),
                );
            }
            "assignment_expression" | "augmented_assignment_expression" => {
                let left = field(node, "left", self.source);
                self.emit(node,"assignment",&format!("{owner}::{left}"),json!({"leftExpression":left,"owner":owner,"resolution":"syntactic-unresolved"}));
            }
            "arkui_component_expression" => {
                self.emit(node, "arkui-component", owner, json!({"owner":owner}));
            }
            _ => {}
        }
        let mut cursor = node.walk();
        for child in node.named_children(&mut cursor) {
            self.visit(child, &scope);
        }
    }
}
pub fn analyze(path: &str, source: &[u8], revision: &str) -> Result<Analysis, String> {
    std::str::from_utf8(source).map_err(|e| e.to_string())?;
    let mut parser = Parser::new();
    parser
        .set_language(&LANGUAGE.into())
        .map_err(|e| e.to_string())?;
    let tree = parser
        .parse(source, None)
        .ok_or("Parser returned no tree")?;
    let root = tree.root_node();
    let mut collector = Collector {
        source,
        path,
        revision,
        rows: Vec::new(),
        occurrences: BTreeMap::new(),
    };
    collector.visit(root, "");
    collector.rows.push(
        json!({"id":format!("ast-file-{}",&digest(path.as_bytes())[..24]),"kind":"parse-file",
        "path":path,"sourceRevision":revision,"sha256":digest(source),"byteLength":source.len(),
        "syntaxHasErrors":root.has_error(),"method":GRAMMAR}),
    );
    collector
        .rows
        .sort_by_key(|r| r["id"].as_str().unwrap().to_owned());
    Ok(Analysis {
        rows: collector.rows,
        has_errors: root.has_error(),
    })
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn state_styles_gap_is_fixed_without_breaking_normal_objects() {
        let source=b"@Component struct Demo { build() { Button() {}.stateStyles({ pressed: { .backgroundColor(Color.Red).borderWidth(2) }, normal: { .opacity(1) } }) } }";
        let mut baseline = Parser::new();
        baseline
            .set_language(&tree_sitter_arkts::LANGUAGE.into())
            .unwrap();
        assert!(baseline
            .parse(source, None)
            .unwrap()
            .root_node()
            .has_error());
        let fixed = analyze("Demo.ets", source, "cut").unwrap();
        assert!(!fixed.has_errors);
        assert!(fixed
            .rows
            .iter()
            .any(|r| r["kind"] == "call" && r["targetExpression"] == "backgroundColor"));
        assert!(
            !analyze(
                "Normal.ts",
                b"const o = { pressed: { color: 'red', width: 2 } };",
                "cut"
            )
            .unwrap()
            .has_errors
        );
        assert!(analyze("Bad.ets",b"@Component struct Bad { build() { Button() {}.stateStyles({ pressed: { .color( } }) } }","cut").unwrap().has_errors);
    }
    #[test]
    fn multiline_import_and_arkui_are_parsed() {
        let source=b"import {\n A,\n B\n} from './module';\n@Component\nstruct Demo {\n @State value: string = '';\n build() { Column() { Text(this.value) } }\n}";
        let result = analyze("Demo.ets", source, "cut").unwrap();
        assert!(!result.has_errors);
        assert!(result
            .rows
            .iter()
            .any(|r| r["kind"] == "module-reference" && r["specifier"] == "./module"));
        assert!(result
            .rows
            .iter()
            .any(|r| r["kind"] == "symbol" && r["symbol"] == "Demo"));
        assert!(result.rows.iter().any(|r| r["kind"] == "arkui-component"));
    }
    #[test]
    fn comments_do_not_create_calls_and_owner_is_retained() {
        let result = analyze(
            "A.ets",
            b"class A { run() { /* fake() */ real(); this.value = 1; } }",
            "cut",
        )
        .unwrap();
        let calls: Vec<_> = result.rows.iter().filter(|r| r["kind"] == "call").collect();
        assert_eq!(calls.len(), 1);
        assert_eq!(calls[0]["targetExpression"], "real");
        assert_eq!(calls[0]["owner"], "A::run");
        assert!(result
            .rows
            .iter()
            .any(|r| r["kind"] == "assignment" && r["leftExpression"] == "this.value"));
    }
    #[test]
    fn whitespace_keeps_ids_and_invalid_syntax_is_evidence() {
        let a = analyze("A.ets", b"function f() { g(); }", "cut").unwrap();
        let b = analyze("A.ets", b"\nfunction f() {\n g();\n}", "cut").unwrap();
        assert_eq!(
            a.rows.iter().map(|r| &r["id"]).collect::<Vec<_>>(),
            b.rows.iter().map(|r| &r["id"]).collect::<Vec<_>>()
        );
        let bad = analyze("Bad.ets", b"class { ???", "cut").unwrap();
        assert!(bad.has_errors);
        assert!(bad.rows.iter().any(|r| r["kind"] == "parse-error"));
    }
}
