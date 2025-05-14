FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Add the current directory to PYTHONPATH
ENV PYTHONPATH=/app

CMD ["python", "src/main.py", "--monitor", "--find-latest", "--respect-saved"] 