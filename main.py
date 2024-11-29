import os
import sys
import logging
import json
from typing import Union
from dotenv import load_dotenv
from pathlib import Path

from . import ContainerManager, DBManager
from . import config, utils, generate_tests
from AutoTestGen import MODELS, ADAPTERS, SUFFIXES
from tkinter import ttk, messagebox, font, filedialog, scrolledtext




def main():
    """Entry point for the app"""
    # Create a logger
    logger = logging.getLogger("AutoTestGen")
    logger.setLevel(logging.INFO)
    # Create console handler
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Ask for language
    # print("Available languages:", ", ".join(ADAPTERS.keys()))
    # language = input("Enter the programming language: ").strip()
    language = "python"#@@@
    if language not in ADAPTERS.keys():
        print(f"Language '{language}' is not supported.")
        sys.exit(1)
    suffix = SUFFIXES[language]

    # Ask for Docker image name
    # image_name = input("Enter Docker image name (e.g., 'python:3.8'): ").strip()
    image_name = "autotestgen:latest"
    if not image_name:
        print("Docker image name cannot be empty.")
        sys.exit(1)

    # Ask for repository directory
    # repo_dir = input("Enter the path to the repository directory: ").strip()
    repo_dir = "/Users/cc/yutong/server/DataProfiler"#@@@
    if not os.path.isdir(repo_dir):
        print(f"Directory '{repo_dir}' does not exist.")
        sys.exit(1)

    # Connect to the database
    logger.info("Connecting to database...")
    try:
        db_path = os.path.join(repo_dir, "autotestgen.db")
        db_manager = DBManager(db_path)
    except Exception as e:
        logger.error(f"Error occurred while connecting to database: {e}")
        sys.exit(1)

    # Start the container
    logger.info("Starting container...")
    try:
        cont_manager = ContainerManager(
            image_name=image_name,
            repo_dir=repo_dir
        )
    except Exception as e:
        logger.error(f"Error occurred while initializing ContainerManager: {e}")
        sys.exit(1)

    # Ask for module to test
    # module_path = input("Enter the path to the module to test: ").strip()
    module_path = "data_profiler.py"#@@@
    sys.path.insert(0, repo_dir)
    if not os.path.isfile(os.path.join(repo_dir, module_path)):
        print(f"File '{module_path}' does not exist.")
        sys.exit(1)
    # Set Adapter
    try:
        _ = utils.set_adapter(language, module_dir=module_path)
        # Set Adapter
        # _ = utils.set_adapter(self.master.language, module_dir=module_path)
        # Check if requirements are met in container
        container_problem = config.ADAPTER.check_reqs_in_container(
            cont_manager.container
        )
        if container_problem:
            messagebox.showerror("Error", container_problem)
            return
    except Exception as e:
        logger.error(f"Error occurred while setting adapter: {e}")
        sys.exit(1)

    # Main loop
    while True:
        # command = input("Enter command (generate, list, exit): ").strip()
        # command = "generate"#@@@
        # if command == "generate":
            # List available functions/classes
            func_names = config.ADAPTER.retrieve_func_defs()
            class_names = config.ADAPTER.retrieve_class_defs()
            print("Available functions:")
            for func in func_names:
                print(f" - {func}")
            print("Available classes and methods:")
            for cls in class_names:
                methods = config.ADAPTER.retrieve_class_methods(cls)
                print(f" - {cls}")
                for method in methods:
                    print(f"    - {method}")

            # Ask for object to test
            # obj_type = input("Do you want to test a function or a class method? (function/method): ").strip()
            obj_type = "method"#@@@   
            if obj_type == "function":
                # obj_name = input("Enter the function name to test: ").strip()
                obj_name = "flatten_board"#@@@
                if obj_name not in func_names:
                    print(f"Function '{obj_name}' not found.")
                    continue
                class_name = None
            elif obj_type == "method":
                # class_name = input("Enter the class name: ").strip()
                class_name = "DataProfiler"#@@@
                if class_name not in class_names:
                    print(f"Class '{class_name}' not found.")
                    continue
                methods = config.ADAPTER.retrieve_class_methods(class_name)
                # method_name = input("Enter the method name: ").strip()
                method_name = "detect_outliers"#@@@
                if method_name not in methods:
                    print(f"Method '{method_name}' not found in class '{class_name}'.")
                    continue
                obj_name = method_name
            else:
                print("Invalid object type.")
                continue

            # Build initial prompt
            try:
                initial_prompt = config.ADAPTER.prepare_prompt(
                    class_name,
                    obj_name
                )
            except Exception as e:
                logger.error(f"Error occurred while preparing initial prompt: {e}")
                continue

            # Authenticate with OpenAI API
            if config.API_KEY is None:
                api_key = input("Enter your OpenAI API key: ").strip()
                if not api_key:
                    print("API key cannot be empty.")
                    continue
                utils.set_api_keys(api_key)

            # Set model
            print("Available models:", ", ".join(MODELS))
            # model = input("Enter the model to use: ").strip()
            model = "gpt-3.5-turbo"#@@@
            if model not in MODELS:
                print(f"Model '{model}' is not available.")
                continue
            utils.set_model(model)
            if obj_type == "method":
                import_name = class_name
            elif obj_type == "function":
                import_name = obj_name
            else:
                messagebox.showerror(
                    "Error",
                    "Please select a class method or function for testing"
                )
                return


            # Generate tests
            try:
                result = generate_tests(
                    initial_prompt,
                    cont_manager,
                    obj_name=import_name,
                    temp=0.1,
                    n_samples=1,
                    max_iter=3,
                    logger=logger
                )
                metadata = result["report"]
                
                filename = f"{class_name}-{obj_name}-tests.json"
                path = os.path.join("test", filename)

                # Open the file in write mode and save the result as JSON
                with open(path, 'w') as json_file:
                    json.dump(result, json_file, indent=4)

                # Save test to database
                db_manager.add_test_to_db(
                    module=os.path.basename(module_path),
                    class_name=class_name,
                    object_name=obj_name,
                    history=json.dumps(result["messages"]),
                    test=result["test"],
                    metadata=json.dumps(metadata)
                )
                logger.info("Tests generated and saved to database.")
            except Exception as e:
                logger.error(f"Error occurred while generating tests: {e}")

        # elif command == "list":
            # List tests in the database
            # tests = db_manager.get_all_tests()
            # for test in tests:
            #     print(f"ID: {test['id']}, Object: {test['object']}, Class: {test['class']}")
        # elif command == "exit":
            # Clean up and exit
            # cont_manager.stop_container()
            # db_manager.close_db()
            break
        # else:
            # print("Unknown command.")

if __name__ == "__main__":
    main()
