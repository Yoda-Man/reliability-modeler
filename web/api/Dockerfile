FROM python:3.11-slim

WORKDIR /app

# Install system dependencies if any
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY ./web/api/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the modeler package from the parent directory
# Note: We'll handle this via Docker context or build args if needed, 
# but for a simple setup we can copy it in.
COPY ./modeler /app/modeler
COPY ./fault_categories.conf /app/fault_categories.conf

# Copy the API code
COPY ./web/api/main.py /app/main.py
COPY ./web/api/sample_data.csv /app/sample_data.csv

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
