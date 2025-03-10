# Testing Cloud Functions with Postman

This guide explains how to test the Medical Text Summarization Cloud Function using Postman.

## Prerequisites

1. [Postman](https://www.postman.com/downloads/) installed on your machine
2. For local testing: Docker running with the cloud function container
3. For test/production: Deployed function URLs and proper authentication

## Testing in Local Environment

When testing locally, the cloud function is accessible via your Docker container.

### Setup

1. Start the local Docker container:

   ```bash
   cd /home/juan/Desktop/Proyecto_AI_Medico/github_medical_web_app/cloud_functions
   docker-compose up
   ```

2. The function will be available at: `http://localhost:8082`

### Health Check Request

You can perform a basic health check using a GET request:

1. Open Postman
2. Create a new HTTP request with the following settings:
   - Method: `GET`
   - URL: `http://localhost:8082`

This will return basic information about the function.

### Text Summarization Request

To summarize medical text:

1. Open Postman
2. Create a new HTTP request with the following settings:

   - Method: `POST`
   - URL: `http://localhost:8082`
   - Headers:
     - `Content-Type`: `application/json`

3. In the request body, select "raw" and "JSON", then add:

   ```json
   {
     "text": "Patient presents with symptoms of fever (101.3°F), persistent cough for 2 weeks, fatigue, and shortness of breath. Chest X-ray shows bilateral infiltrates consistent with pneumonia. O2 saturation is 94% on room air. Patient has history of asthma but no other significant conditions. Started on azithromycin and albuterol. Follow-up appointment scheduled for next week. Patient advised to return if symptoms worsen or if breathing becomes more difficult."
   }
   ```

4. Click "Send" to submit the request

### Expected Response

You should receive a JSON response similar to:

## Testing Document Update Feature

You can test updating a document in your Django application by including a `document_id` in your request:

## Troubleshooting Common Errors

### UsageMetadata Errors

If you encounter an error like:
