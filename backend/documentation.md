2. **Security Flow:**

   - For local development: Uses Google Cloud Secret Manager directly
   - For CI/CD: Uses GitHub Actions secrets injected as environment variables
   - Fallback to SQLite if neither is available (development safety net)

3. **GitHub Secrets Required:**

   - `TEST_DB_NAME`: optional
   - `TEST_DB_USER`: optional
   - `TEST_DB_PASSWORD`: optional
   - `TEST_DB_HOST`: optional
   - `TEST_DB_PORT`: optional
   - `GCP_SA_KEY`: Service account key with Secret Manager access
   - `stg_vpc_connector_name`: github variable

4. **Google Secrets Required:**
   - `django-secret-key`: Django's secret key for staging
   - `db-name`: Database name
   - `db-user`: Database username
   - `db-password`: Database password
   - `db-host`: Database host
