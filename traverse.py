import os
import sys
import logging
import json
import importlib.util
from typing import Union
from dotenv import load_dotenv
from pathlib import Path
import argparse

from . import ContainerManager, DBManager
from . import config, utils, generate_tests
from AutoTestGen import MODELS, ADAPTERS, SUFFIXES

def generate_test_for_object(module_path, class_name, obj_name, obj_type, cont_manager, db_manager, logger, language, repo_dir, model):
    logger.info(f"Generating tests for {obj_type}: {obj_name} in module {module_path}")

    # Prepare the initial prompt
    try:
        if obj_type == 'function':
            initial_prompt = config.ADAPTER.prepare_prompt(obj_name, class_name)
        else:
            initial_prompt = config.ADAPTER.prepare_prompt(class_name, obj_name)
        # initial_prompt = config.ADAPTER.prepare_prompt(obj_name, class_name)
    except Exception as e:
        logger.error(f"Error occurred while preparing initial prompt for {obj_name}: {e}")
        return

    # Set the import name based on the object type
    import_name = class_name if obj_type == 'method' else obj_name

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
        
        # Create a unique filename for each test
        class_part = class_name if class_name else 'module'
        filename = f"{class_part}-{obj_name}-tests.json"
        # Ensure the directory exists
        test_dir = os.path.join(repo_dir, 'test')
        os.makedirs(test_dir, exist_ok=True)
        model_dir = os.path.join(test_dir, model)
        os.makedirs(model_dir, exist_ok=True)

        path = os.path.join(model_dir, filename)

        # Save the result as JSON
        with open(path, 'w') as json_file:
            json.dump(result, json_file, indent=4)

        # Save test to the database
        db_manager.add_test_to_db(
            module=os.path.basename(module_path),
            class_name=class_name,
            object_name=obj_name,
            history=json.dumps(result.get("messages", [])),
            test=result.get("test", ""),
            metadata=json.dumps(metadata)
        )
        logger.info(f"Tests generated and saved for {obj_name}")
    except Exception as e:
        logger.error(f"Error occurred while generating tests for {obj_name}: {e}")

def process_module(module_path, cont_manager, db_manager, logger, repo_dir, language, model):
    logger.info(f"Processing module: {module_path}")
    
    # Adjust the adapter to the new module
    try:
        # Add the module's directory to sys.path
        module_full_path = os.path.join(repo_dir, module_path)
        module_dir = os.path.dirname(module_full_path)
        if module_dir not in sys.path:
            sys.path.insert(0, module_dir)

        # Import the module
        module_name = os.path.splitext(os.path.basename(module_path))[0]
        spec = importlib.util.spec_from_file_location(module_name, module_full_path)
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.error(f"Error importing module {module_name}: {e}")
            return

        utils.set_adapter(language, module_dir=module_path)
        # Check if requirements are met in container
        container_problem = config.ADAPTER.check_reqs_in_container(cont_manager.container)
        if container_problem:
            logger.error(f"Container problem: {container_problem}")
            return
    except Exception as e:
        logger.error(f"Error occurred while setting adapter for module {module_path}: {e}")
        return

    # Retrieve functions and classes
    try:
        func_names = config.ADAPTER.retrieve_func_defs()
        class_names = config.ADAPTER.retrieve_class_defs()
    except Exception as e:
        logger.error(f"Error occurred while retrieving definitions from module {module_path}: {e}")
        return

    # Generate tests for functions
    for func_name in func_names:
        generate_test_for_object(module_path, None, func_name, 'function', cont_manager, db_manager, logger, language, repo_dir, model)

    # Generate tests for class methods
    for class_name in class_names:
        try:
            methods = config.ADAPTER.retrieve_class_methods(class_name)
        except Exception as e:
            logger.error(f"Error occurred while retrieving methods from class {class_name}: {e}")
            continue
        for method_name in methods:
            generate_test_for_object(module_path, class_name, method_name, 'method', cont_manager, db_manager, logger, language, repo_dir, model)

def main():
    """Entry point for the app"""
    # Create the argument parser
    parser = argparse.ArgumentParser(description='AutoTestGen Script')
    
    # Add arguments
    parser.add_argument('--language', type=str, default='python', help='Programming language (default: python)')
    parser.add_argument('--image_name', type=str, default='autotestgen:latest', help='Docker image name (default: autotestgen:latest)')
    parser.add_argument('--repo_dir', type=str, required=True, help='Path to the repository directory')
    parser.add_argument('--model', type=str, default='gpt-3.5-turbo', help='OpenAI model to use (default: gpt-3.5-turbo)')
    parser.add_argument('--api_key', type=str, default=None, help='OpenAI API key')
    
    # Parse the arguments
    args = parser.parse_args()
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
    language = "python"  # Or prompt the user
    if language not in ADAPTERS.keys():
        print(f"Language '{language}' is not supported.")
        sys.exit(1)
    suffix = SUFFIXES[language]

    # Ask for Docker image name
    image_name = args.image_name  # Or prompt the user
    if not image_name:
        print("Docker image name cannot be empty.")
        sys.exit(1)

    # Ask for repository directory
    repo_dir = args.repo_dir  # Or prompt the user #@@@
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

    # Authenticate with OpenAI API
    if config.API_KEY is None:
        api_key = input("Enter your OpenAI API key: ").strip()
        if not api_key:
            print("API key cannot be empty.")
            sys.exit(1)
        utils.set_api_keys(api_key)

    # Set model
    model = args.model  # Or prompt the user #@@@
    if model not in MODELS:
        print(f"Model '{model}' is not available.")
        sys.exit(1)
    utils.set_model(model)

    # Traverse all Python files in the repository
    for root, dirs, files in os.walk(repo_dir):
        # Exclude directories you don't want to process
        dirs[:] = [d for d in dirs if d not in ['__pycache__', 'venv', 'env', '.git']]
        for file in files:
            if file.endswith('.py'):
                module_full_path = os.path.join(root, file)
                relative_module_path = os.path.relpath(module_full_path, repo_dir)
                
                # Now process this module
                process_module(relative_module_path, cont_manager, db_manager, logger, repo_dir, language, model)
    
    # Clean up
    cont_manager.stop_container()
    db_manager.close_db()

if __name__ == "__main__":
    main()
