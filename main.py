import argparse
import ast
import os
import fastapi
import uvicorn

app = fastapi.FastAPI()

def extract_routes_from_file(file_path, file_name, app_name):
    with open(file_path, "r") as source:
        tree = ast.parse(source.read())

    routes = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    if (
                        isinstance(decorator.func, ast.Attribute)
                        and decorator.func.attr == "whitelist"
                    ):
                        methods_arg = None
                        params = []

                        for kw in decorator.keywords:
                            if kw.arg == "methods":
                                methods_arg = kw.value
                                break

                        if isinstance(methods_arg, ast.List):
                            methods = [method.s for method in methods_arg.elts]
                        elif isinstance(methods_arg, ast.Constant):
                            methods = [methods_arg.value]
                        else:
                            methods = ["POST"]

                        for arg, default in zip(
                            node.args.args,
                            node.args.defaults
                            + [None] * (len(node.args.args) - len(node.args.defaults)),
                        ):
                            param_name = arg.arg
                            is_optional = default is not None
                            param_in = (
                                "body"
                                if "POST" in methods or "PUT" in methods
                                else "query"
                            )

                            params.append(
                                {
                                    "name": param_name,
                                    "in": param_in,
                                    "required": not is_optional,
                                    "schema": {"type": "string"},
                                }
                            )

                        docstring = ast.get_docstring(node) or ""
                        doc_summary = docstring.splitlines()[0] if docstring else ""

                        route = {
                            "function_name": node.name,
                            "path": f"/api/methods/{app_name.lower()}.api.{file_name}.{node.name}",
                            "method": methods,
                            "params": params,
                            "doc": doc_summary,
                            "responses": {},
                            "tag": file_name,
                        }
                        routes.append(route)

    return routes


def generate_openapi_spec(routes, app_name):
    openapi_schema = {
        "openapi": "3.0.0",
        "info": {
            "title": f"{app_name} API",
            "version": "1.0.0",
        },
        "paths": {},
    }

    tags = set()

    for route in routes:
        path = route["path"]
        methods = route["method"]
        doc = route["doc"]
        params = route["params"]
        responses = route["responses"]
        tag = route["tag"]

        # Add tag to the set of tags
        tags.add(tag)

        for method in methods:
            if path not in openapi_schema["paths"]:
                openapi_schema["paths"][path] = {}

            openapi_schema["paths"][path][method.lower()] = {
                "summary": doc,
                "description": doc,
                "parameters": params if method not in ["POST", "PUT"] else [],
                "requestBody": {
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    param["name"]: param["schema"] for param in params
                                },
                                "required": [
                                    param["name"]
                                    for param in params
                                    if param["required"]
                                ],
                            }
                        }
                    }
                }
                if method in ["POST", "PUT"]
                else None,
                "responses": responses or {"200": {"description": "Successful Response"}},
                "tags": [tag],
            }

    openapi_schema["tags"] = [{"name": tag} for tag in tags]

    return openapi_schema

def extract_routes_from_module(module_path, app_name):
    all_routes = []

    for root, dirs, files in os.walk(module_path):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                file_name = os.path.splitext(file)[0]
                routes = extract_routes_from_file(file_path, file_name, app_name)
                all_routes.extend(routes)

    return all_routes

def custom_openapi(module_path, app_name):
    routes = extract_routes_from_module(module_path, app_name)
    openapi_schema = generate_openapi_spec(routes, app_name)

    return openapi_schema

def set_openapi(module_path, app_name):
    app.openapi = lambda: custom_openapi(module_path, app_name)

def main():
    parser = argparse.ArgumentParser(
        description="Run FastAPI app with custom OpenAPI from a module."
    )
    parser.add_argument(
        "app_name",
        help="Name of the FastAPI app, used in the documentation title and paths",
    )
    parser.add_argument(
        "module",
        help="Path to the module containing Python files to extract routes from",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="Host to run the FastAPI app on"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port to run the FastAPI app on"
    )
    args = parser.parse_args()

    set_openapi(args.module, args.app_name)

    uvicorn.run(app, host=args.host, port=args.port)

if __name__ == "__main__":
    main()

