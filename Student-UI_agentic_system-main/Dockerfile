FROM python:3.12-slim

WORKDIR /app
COPY requirements-client.txt .
RUN pip install --no-cache-dir -r requirements-client.txt

COPY app.py .
COPY public/ public/
COPY chainlit.md .
COPY .chainlit/ .chainlit/

EXPOSE 8000
CMD ["chainlit", "run", "app.py", "-h", "--host", "0.0.0.0", "--port", "8000"]
