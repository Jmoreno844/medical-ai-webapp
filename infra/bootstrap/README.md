# Bootstrap manual de Terraform en GCP

Este bootstrap se hace **una sola vez por proyecto** para que Terraform pueda usar un backend remoto en GCS y autenticarse con una service account dedicada.

Proyecto objetivo inicial: `vext-stg`  
Region principal: `us-east1`

## Prerrequisito: facturación

GCS (bucket de `tfstate`) y varios servicios exigen un **proyecto con facturación activa**. Si ves `The billing account for the owning project is disabled`, en [Google Cloud Console](https://console.cloud.google.com/billing) vincula una cuenta de facturación al proyecto y vuelve a ejecutar los pasos desde la sección 4 (crear bucket).

## 1. Variables base

```bash
export PROJECT_ID="vext-stg"
export REGION="us-east1"
export TFSTATE_BUCKET="${PROJECT_ID}-terraform-state"
export TERRAFORM_SA="terraform-admin"
```

## 2. Seleccionar el proyecto

```bash
gcloud config set project "${PROJECT_ID}"
```

## 3. Habilitar APIs minimas para bootstrap

```bash
gcloud services enable \
  iam.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  storage.googleapis.com \
  sts.googleapis.com
```

## 4. Crear bucket de estado remoto

```bash
gcloud storage buckets create "gs://${TFSTATE_BUCKET}" \
  --location="${REGION}" \
  --uniform-bucket-level-access
```

Habilitar versionado del estado:

```bash
gcloud storage buckets update "gs://${TFSTATE_BUCKET}" \
  --versioning
```

## 5. Crear service account de Terraform

```bash
gcloud iam service-accounts create "${TERRAFORM_SA}" \
  --display-name="Terraform Admin"
```

```bash
export TERRAFORM_SA_EMAIL="${TERRAFORM_SA}@${PROJECT_ID}.iam.gserviceaccount.com"
```

## 6. Permisos iniciales del bootstrap

Estos permisos son amplios porque el objetivo es levantar el proyecto desde cero, incluido IAM, Workload Identity Federation, Cloud Run, Cloud Functions, Cloud SQL, Storage y Secret Manager.

```bash
for ROLE in \
  roles/editor \
  roles/resourcemanager.projectIamAdmin \
  roles/iam.serviceAccountAdmin \
  roles/iam.serviceAccountKeyAdmin \
  roles/iam.workloadIdentityPoolAdmin \
  roles/serviceusage.serviceUsageAdmin \
  roles/storage.admin
do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${TERRAFORM_SA_EMAIL}" \
    --role="${ROLE}"
done
```

## 7. Acceso al bucket de tfstate

```bash
gcloud storage buckets add-iam-policy-binding "gs://${TFSTATE_BUCKET}" \
  --member="serviceAccount:${TERRAFORM_SA_EMAIL}" \
  --role="roles/storage.admin"
```

## 8. Opcion temporal: clave JSON solo para el primer apply

Si todavia no existe Workload Identity Federation, puedes crear **temporalmente** una clave JSON local para el primer `terraform apply`.

```bash
mkdir -p ./.secrets
gcloud iam service-accounts keys create "./.secrets/${PROJECT_ID}-terraform-admin.json" \
  --iam-account="${TERRAFORM_SA_EMAIL}"
```

Exportar la credencial temporal:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/.secrets/${PROJECT_ID}-terraform-admin.json"
```

## 9. Inicializar Terraform con backend remoto

Desde `infra/environments/test`:

```bash
terraform init \
  -backend-config="bucket=${TFSTATE_BUCKET}" \
  -backend-config="prefix=terraform/test"
```

## 10. Despues del primer apply

Una vez que Workload Identity Federation quede creada y probada:

1. Revoca la clave JSON temporal.
2. Elimina el archivo local.
3. Usa solo WIF para CI/CD y aplica local si realmente hace falta.

Revocar claves:

```bash
gcloud iam service-accounts keys list \
  --iam-account="${TERRAFORM_SA_EMAIL}"
```

```bash
gcloud iam service-accounts keys delete KEY_ID \
  --iam-account="${TERRAFORM_SA_EMAIL}"
```

## Recordatorios de seguridad

- No subas `./.secrets/` al repo.
- Mantén el bucket de `tfstate` privado.
- Usa WIF en GitHub Actions; evita `GCP_SA_KEY` de larga vida.
- Si mas adelante separas `test` y `prod`, repite este bootstrap por proyecto o usa un proyecto separado para estado remoto compartido.
