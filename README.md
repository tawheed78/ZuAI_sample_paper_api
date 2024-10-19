# Sample Paper API

## Overview
The **Sample Paper API** is a fast, scalable solution for performing CRUD operations with Sample papers along with extracting content from PDF files and Plain Text in a specified schema and saving the results to a database. This project is built using FastAPI, MongoDB, Redis for caching and integrates GeminiAI services to generate sample papers based on the extracted content. Background tasks are utilized to handle long-running PDF processing asynchronously, allowing users to check the status of their tasks via API.

## Features
- **CRUD Operations**: Create, Update, Retrieve or Delete a Sample Paper.
- **PDF File Extraction**: Upload PDF files to be processed asynchronously and extract relevant information.
- **Plain Text Extraction**: Upload Plain Text to be processed synchronously and extract relevant information.
- **Background Task Handling**: Long-running PDF extraction tasks are handled in the background, improving API responsiveness.
- **Task Status Checking**: Users can check the status of their PDF extraction tasks using the provided task ID.
- **Error Handling**: Graceful error handling for common issues, such as file format validation, database errors, and task failures.
- **Rate Limiting**: Prevents abuse by limiting the number of PDF uploads per minute.
- **API Documentation**: Interactive API documentation is provided via Swagger UI and Redoc.

---

## Table of Contents
- [Installation](#installation)
- [API Endpoints](#api-endpoints)
- [Technologies Used](#technologies-used)
- [Environment Variables](#environment-variables)
- [How It Works](#how-it-works)
- [Rate Limiting](#rate-limiting)
- [Error Handling](#error-handling)
- [Contributing](#contributing)
- [License](#license)

---

## Installation

### Prerequisites
Before you begin, ensure you have the following installed:
- **Python 3.8+**
- **MongoDB** (for storing task and extraction information)
- **Redis** (for caching frequently accessed data and storing Rate Limiting Counter)

### 1. Clone the Repository and create a virtual environment
```bash
git clone https://github.com/yourusername/ZuAI_sample_paper_api.git
python -m venv venv
venv\Scripts\activate
cd sample-paper-api

### 2. Install Dependencies
```bash
pip install -r requirements.txt

### 3. Create a .env file in the root directory with the following content
```bash
MONGO_URI
GEMINI_API_KEY

### 4. Start the Backend Server and spin a Redis server as well
```bash
uvicorn app.main:app --reload
redis-server (localhost)


