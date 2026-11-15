import tree_sitter_python as ts_py
import tree_sitter_javascript as ts_js
from tree_sitter import Language , Parser

py_lang = Language(ts_py.language())

parser = Parser(py_lang)

tree = parser.parse(
    bytes(
        """
def foo():
    if bar:
        baz()
""",
        "utf8"
    )
)

print(tree.root_node.named_children[0].named_children[0].child_by_field_name("value"))

