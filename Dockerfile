# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Run gunicorn as the production application server 
# This runs the Flask app defined in app.py:app
# Use a simple, robust command line configuration for App Service
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "app:app"]