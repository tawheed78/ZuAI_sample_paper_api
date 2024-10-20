"""
Sample paper routes for ZuAI Sample Paper FastAPI application.

This module defines the API endpoints for extracting data for
sample papers from PDF and Plain Text Input.
"""
import json
import os
import aiofiles
import string
import google.generativeai as genai
from bson import ObjectId
from pydantic import ValidationError
from dotenv import load_dotenv
from pymongo.errors import PyMongoError

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Body, HTTPException,File, Request, UploadFile, BackgroundTasks

from ..rate_limiter import rate_limit
from ..models import PaperModel, TaskStatusResponseModel
#from ..config import db, INSTRUCTION, PROMPT, safe
from ..configs.database import db
from ..configs.gemini_inputs import INSTRUCTION, PROMPT, safe
from ..configs.logs import logger

load_dotenv()

paper_collection = db['sample_papers']
task_collection = db['task_status']

genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel(
    model_name="models/gemini-1.5-flash",
    system_instruction=INSTRUCTION,
    generation_config=({"response_mime_type": "application/json"}),
    safety_settings = safe)

router = APIRouter()

def update_task_status(task_id, status, description):
    """
    Update the status of a background task in the database.

    This function updates the status and description of a task in the task collection.

    Args:
        task_id (str): The ID of the task to update.
        status (str): The new status for the task.
        description (str): A description providing additional information about the task's status.
    """
    logger.info(f"Updating task status for task_id: {task_id}, status: {status}")
    query = {"_id":ObjectId(task_id)}
    update_data = {"$set": {"status": status, "description":description}}
    task_collection.update_one(query, update_data)

def generate_sample_paper(sample_pdf, task_id: str):
    """
    Generate a sample paper using the Generative AI model.

    This function takes a PDF file and generates a sample paper based on its content.

    Args:
        sample_pdf (str): The PDF file content to be processed.
        task_id (str): The ID of the task for logging purposes.

    Returns:
        str: The generated sample paper content.

    Raises:
        Exception: If there is an error during content generation.
    """
    logger.info(f"Generating sample paper for task_id: {task_id}")
    try:
        response = model.generate_content([PROMPT, sample_pdf])
        if response.parts:
            response_text = response.text
            response = response_text
            return response
    except Exception as e:
        logger.error(f"Error during content generation for task_id: {task_id}: {e}")
        update_task_status(task_id, status='Failed', description="Error during Content generation")

def insert_sample_paper(response: dict, task_id: str):
    """
    Insert the generated sample paper into the MongoDB collection.

    This function takes the generated paper response and inserts it into the sample papers collection.

    Args:
        response (dict): The generated sample paper data.
        task_id (str): The ID of the task for logging purposes.

    Raises:
        ValidationError: If the generated data does not conform to the PaperModel schema.
        PyMongoError: If there is an error while inserting the data into MongoDB.
        Exception: For any other unexpected errors.
    """
    logger.info(f"Inserting sample paper into the database for task_id: {task_id}")
    try:
        sample_paper = PaperModel(**response)
        paper_collection.insert_one(sample_paper.model_dump())
        logger.info(f"Sample paper inserted successfully for task_id: {task_id}")
        return True
    except ValidationError as ve:
        logger.error(f"Validation error for task_id: {task_id}: {ve}")
        update_task_status(task_id, status='Failed', description="Invalid response received")
    except PyMongoError as pme:
        logger.error(f"Database error for task_id: {task_id}: {pme}")
        update_task_status(task_id, status='Failed', description="Database error")
    except Exception as e:
        logger.error(f"Internal Server error for task_id: {task_id}: {e}")
        update_task_status(task_id, status="Failed", description="Internal Server Error")

def pdf_extraction_background_task(file_location: str, task_id:str):
    """
    Background task to process PDF extraction and insert the generated sample paper into the database.

    This function handles the PDF extraction process and generates a sample paper from it.

    Args:
        file_location (str): The location of the PDF file to process.
        task_id (str): The ID of the task for logging purposes.

    Raises:
        Exception: If there are errors during PDF extraction or sample paper insertion.
    """
    logger.info(f"Starting background task for PDF extraction for task_id: {task_id}")
    try:
        sample_pdf = genai.upload_file(file_location)
        response = generate_sample_paper(sample_pdf, task_id)
        if response:
            try:
                response = json.loads(response)
            except json.JSONDecodeError as json_err:
                logger.error(f"JSON decode error for task_id: {task_id}: {json_err}")
                update_task_status(task_id, status='Failed', description="Invalid JSON Response")
            response = insert_sample_paper(response, task_id)
            if response:
                update_task_status(task_id, status='Completed',
                description="Sample paper extracted and saved successfully")
            update_task_status(task_id, status='Failed', description="Invalid JSON Response received from generator")
    except PyMongoError as pme:
        logger.error(f"Database error for task_id: {task_id}: {pme}")
        update_task_status(task_id, status='Failed', description="Database error occured")
    except Exception as e:
        logger.error(f"Internal Server error for task_id: {task_id}: {e}")
        update_task_status(task_id, status='Failed', description="Internal Server error")

@router.post('/extract/pdf')
@rate_limit(limit=2, time_window=60)
async def extract_pdf(
    request:Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
    ):
    """
    Handle PDF file upload and initiate a background task for extraction.

    This endpoint allows the user to upload a PDF file, which will be processed in the background.

    Args:
        request (Request): The incoming request object.
        background_tasks (BackgroundTasks): The background tasks manager to handle long-running tasks.
        file (UploadFile): The uploaded PDF file.

    Returns:
        JSONResponse: A response indicating the status of the request.

    Raises:
        HTTPException: If the file type is invalid or if an error occurs during processing.
    """
    logger.info(f"Received PDF extraction request: {file.filename}")
    try:
        if file.content_type != "application/pdf":
            logger.warning("Invalid file type uploaded. Only PDFs are allowed.")
            raise HTTPException(status_code=400, detail="Only PDF files are allowed.")
        file_location = f"data/input/{file.filename}"
        os.makedirs(os.path.dirname(file_location), exist_ok=True)
        async with aiofiles.open(file_location, 'wb') as out_file:
            content = await file.read()
            await out_file.write(content)
        try:
            query = {"status": "In Progress", "description": "PDF extraction is in process..."}
            task = await task_collection.insert_one(query)
            task_id = task.inserted_id
            logger.info(f"Task created for PDF extraction, task_id: {task_id}")
        except Exception as e:
            logger.error(f"Error initializing task for PDF extraction: {e}")
            raise HTTPException(status_code=500, detail="Error initializing task") from e
        background_tasks.add_task(pdf_extraction_background_task, file_location, task_id)
        return JSONResponse(status_code=202,
            content={"message": f"The request for PDF extraction is accepted and is under progress.Please check the task status using Task ID: {task_id}"})
    except Exception as e:
        logger.error(f"Operation failed due to internal error for task_id: {task_id}: {e}")
        await update_task_status(task_id, status='Failed', description="Operation failed due to internal error.")
        raise HTTPException(status_code=500, detail="Operation failed due to internal error.") from e
    
@router.post('/extract/text')
@rate_limit(limit=3, time_window=60)
async def extract_text(request:Request, input_data: str = Body(...)):
    """
    Extract and process 'SINGLE LINE' text input to generate a sample paper using the AI model.

    This endpoint takes plain text input and generates a sample paper based on the content. Convert a PDF
    to plain text and then remove all the newlines and use it as a input.

    Args:
        request (Request): The incoming request object.
        input_data (str): The plain text input provided by the user.

    Returns:
        dict: A response indicating the successful extraction and saving of the sample paper.

    Raises:
        HTTPException: If the input is invalid or an error occurs during processing.
    """
    logger.info("Received text extraction request")
    try:
        if not isinstance(input_data, str):
            logger.warning("Invalid input type. Only plain text is allowed.")
            raise HTTPException(status_code=400, detail="Only plain text are allowed.")
        response = model.generate_content([PROMPT, input_data])
        response = response.text
        try:
            sample_paper = PaperModel(**json.loads(response))
        except ValidationError as ve:
            logger.error(f"Validation error: {ve}")
            raise HTTPException(status_code=422, detail="Data Validation error occured.") from ve
        paper_collection.insert_one(sample_paper.model_dump())
        logger.info("Sample paper extracted and saved successfully")
        return {"message": "Sample paper extracted and saved successfully"}
    except json.JSONDecodeError as exc:
        logger.error(f"Invalid JSON response from model: {exc}")
        raise HTTPException(status_code=400, detail="Invalid JSON response from model.") from exc
    except Exception as e:
        logger.error(f"Internal Server Error: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error.") from e

@router.get('/tasks/{task_id}', response_model=TaskStatusResponseModel)
async def task_status(task_id: str):
    """
    Retrieve the status of a background task by its ID.

    This endpoint checks the status and description of a task identified by the given task ID.

    Args:
        task_id (str): The ID of the task to check the status for.

    Returns:
        TaskStatusResponseModel: The status and description of the specified task.

    Raises:
        HTTPException: If the task ID is invalid or the task does not exist.
    """
    logger.info(f"Checking task status for task_id: {task_id}")
    try:
        if not ObjectId.is_valid(task_id):
            logger.warning(f"Invalid Task ID format: {task_id}")
            raise HTTPException(status_code=400, detail="Invalid Task ID format")
        query = {"_id": ObjectId(task_id)}
        task = await task_collection.find_one(query)
        if not task:
            logger.warning(f"No such task exists: {task_id}")
            raise HTTPException(status_code=400, detail="No such Task exists")
        task_status = task.get("status", "Unknown. Please wait as we are looking into the issue...")
        task_description = task.get("description", "Unknown. Please wait as we are looking into the issue...")
        return TaskStatusResponseModel(task_id=task_id, status=task_status, description=task_description)
    except ValidationError as ve:
        logger.error(f"Validation error for task_id: {task_id}: {ve}")
        raise HTTPException(status_code=422, detail="Invalid input data") from ve
    except PyMongoError as pme:
        logger.error(f"Database error for task_id: {task_id}: {pme}")
        raise HTTPException(status_code=503, detail="Database error occured.") from pme
    except Exception as e:
        logger.error(f"Internal Server error for task_id: {task_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal Server error") from e
