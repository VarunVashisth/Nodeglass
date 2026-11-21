import tree_sitter_python as ts_py
import tree_sitter_javascript as ts_js
from tree_sitter import Language , Parser
from pathlib import Path 

LANGUAGE = {
    "python": Language(ts_py.language()),
    "javascript": Language(ts_js.language()),
}

EXTENSIONS = {
    ".py":"python",
    ".js":"javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
}

FUNCTION_TYPES = {
    "python": {"function_definition"},
    "javascript": {"function_declaration"},
}



def parse_file(filename):
    
    """_summary_

    Args:
        filename (_type_): code file 

    Raises:
        ValueError: unsupported file extension

    Returns:
         language detected , file code in bytes , syntax tree 
    """
    
    path=Path(filename)
    language_name = EXTENSIONS.get(path.suffix.lower())
    
    if language_name is None:
        raise ValueError(f"Unsupported file extension: {path.suffix}")
    
    source = path.read_bytes()
    parser = Parser(LANGUAGE[language_name])
    tree = parser.parse(source)
    
    return language_name, source, tree 
     


def extract_functions(language , source , tree):
    results = []
    stack = [tree.root_node]
    
    while stack : 
        node = stack.pop()
        
        if node.type in FUNCTION_TYPES[language]:
            name = node.child_by_field_name("name")
            
            results.append({
                "kind": "function",
                "name": (
                    source[name.start_byte:name.end_byte].decode("utf-8")
                    if name else None
                ),
                "start_line": node.start_point.row + 1,
                "end_line": node.end_point.row + 1,
                "code": source[node.start_byte:node.end_byte].decode("utf-8"),
            })
        
        stack.extend(reversed(node.named_children))
        
        
    return results


file_name = "/home/varizz/Nodeglass/backend/parsers/test.py"

lang_name , source , tree = parse_file(file_name)

result = extract_functions(lang_name , source , tree )

print(result)