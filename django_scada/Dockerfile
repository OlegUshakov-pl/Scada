FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY . .
# Django 6.1.1 requires Python 3.12+; 3.14-slim is recommended
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
