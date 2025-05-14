FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nft_scanner.py .

ENTRYPOINT ["python", "nft_scanner.py"] 