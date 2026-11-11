# #90 — Private S3 storage for profile pictures (staging first)

This runbook is **not** an automated deployment. It describes a manual AWS change that must be checked against the team's current account and instance profiles. Do not add AWS keys to GitHub or Elastic Beanstalk environment properties.

## Intended behavior

- Public **access to the bucket stays blocked**. User profile photo URLs returned by Django are temporary, signed S3 URLs (valid for 300 seconds).
- Django uploads with `django-storages` using the **Elastic Beanstalk EC2 instance role**, not credentials embedded in the application.
- Staging and production should have **different media buckets** so a staging test or deletion cannot affect production media.
- `static/frontend` and WhiteNoise static files remain unchanged.
- The existing code supports S3 via `AWS_STORAGE_BUCKET_NAME`; the patch for #90 enables signed URLs when that variable is set.

## Preconditions

- The EB application is `semesterpilot`, AWS region is `us-east-2`.
- Existing EB environments are `semesterpilot-staging` and `semesterpilot-prod`.
- Export `AWS_PROFILE=eb-cli` and `AWS_DEFAULT_REGION=us-east-2` in the **local shell**.
- Check current AWS caller identity. Do not paste key material or `DATABASE_PASSWORD`/other secret values into a PR.
- Get approval before modifying production IAM, EB configuration, or storage.

## 1. Read-only inventory

```bash
export AWS_PROFILE=eb-cli
export AWS_DEFAULT_REGION=us-east-2
aws sts get-caller-identity

for ENV in semesterpilot-staging semesterpilot-prod; do
  echo "=== $ENV ==="
  aws elasticbeanstalk describe-configuration-settings \
    --application-name semesterpilot --environment-name "$ENV" \
    --query "ConfigurationSettings[0].OptionSettings[?OptionName=='IamInstanceProfile' || OptionName=='AWS_STORAGE_BUCKET_NAME' || OptionName=='AWS_S3_REGION_NAME'].[OptionName,Value]" \
    --output table
done

# Confirm region and existing buckets without exposing secrets.
aws s3api list-buckets --query 'Buckets[].Name' --output table
```

The instance profile name is usually an IAM **instance profile**, not necessarily the same name as its underlying IAM role. Resolve it before attaching any policy:

```bash
aws iam get-instance-profile --instance-profile-name PROFILE_NAME \
  --query 'InstanceProfile.Roles[].RoleName' --output table
```

Replace `PROFILE_NAME` with the observed value. If staging and production share the **same IAM role**, consider using separate narrowly scoped policies and confirm the role's effective combined permissions. Do not alter an unknown shared role blindly.

## 2. Create or choose a private staging bucket

Use a globally unique approved name, for example `semesterpilot-staging-media-ACCOUNTID` (replace ACCOUNTID; do not literally copy it). **Do not run create-bucket** if the bucket already exists.

```bash
BUCKET="REPLACE_WITH_APPROVED_UNIQUE_STAGING_BUCKET"
aws s3api create-bucket --bucket "$BUCKET" --region us-east-2 \
  --create-bucket-configuration LocationConstraint=us-east-2

aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
aws s3api put-bucket-encryption --bucket "$BUCKET" \
  --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
aws s3api put-bucket-versioning --bucket "$BUCKET" \
  --versioning-configuration Status=Enabled

aws s3api get-public-access-block --bucket "$BUCKET"
aws s3api get-bucket-location --bucket "$BUCKET"
```

Keep **Block Public Access** enabled. Signed URLs work for private objects without public-read bucket policies or ACLs.

## 3. IAM policy for the EB instance role

Attach an approved IAM policy to the actual EB **instance role**, scoped to the chosen bucket. It needs write/read/delete for uploaded objects; the least-privilege base is:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ProfilePictureObjects",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::REPLACE_WITH_APPROVED_UNIQUE_STAGING_BUCKET/profile-pictures/*"
    },
    {
      "Sid": "ListProfilePictures",
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::REPLACE_WITH_APPROVED_UNIQUE_STAGING_BUCKET",
      "Condition": {"StringLike": {"s3:prefix": ["profile-pictures/*"]}}
    }
  ]
}
```

If the IAM administrator scopes a policy differently, verify the effective permissions. The app's S3 client resolves instance-role credentials with boto3; do **not** set IAM access keys as EB environment properties.

## 4. Configure **staging** only

From AWS EB console → `semesterpilot-staging` → Configuration → Updates/Software → Environment properties, set:

```
AWS_STORAGE_BUCKET_NAME=REPLACE_WITH_APPROVED_UNIQUE_STAGING_BUCKET
AWS_S3_REGION_NAME=us-east-2
```

Do not replace existing configuration wholesale or erase other properties. Modifying environment properties triggers an environment update: inspect EB events and wait for **Ready / Green**.

Alternatively, use a carefully scoped `eb setenv` only if you understand its effects on the team's existing environment configuration. Never paste secret values into shell history.

## 5. Staging acceptance tests

1. Check `eb status semesterpilot-staging` is Ready / Green, and log in to an ordinary staging account.
2. Upload a small (<2 MB) JPG/PNG/GIF via Edit profile.
3. Refresh; the image should still render. Check the image URL points to the expected S3 bucket and includes temporary signing parameters (`X-Amz-Algorithm` / `X-Amz-Expires=300`).
4. Confirm the object exists under `profile-pictures/` with `aws s3api list-objects-v2 --bucket "$BUCKET" --prefix profile-pictures/`.
5. Check unsigned access is blocked; an anonymous unsigned object URL must not return the file (403 expected).
6. Replace the image; confirm its new object is present and the old object's removal behavior is correct. Delete the image; verify the object is removed.
7. Upload a valid image between **1 and 2 MB** to verify nginx permits it. An image **over 2 MB** should receive Django's validation error instead of nginx 413; no object should be created for a rejected upload.
8. With team approval, redeploy staging and verify the image still renders. Check EB health and web logs.

If profile-picture URLs are returned to other users, verify privacy settings (#31 / PR #108) and access behavior before declaring user privacy complete. Signed URLs restrict time but **do not revoke a link already shared** until expiry.

## 6. Production rollout (separate approved change)

Only after staging passes: create a distinct private production bucket with equivalent scoped IAM permissions, check production instance profile, configure production's `AWS_STORAGE_BUCKET_NAME` and `AWS_S3_REGION_NAME`, and verify upload/refresh without touching staging objects. Before any production change, confirm the release window, backup/rollback plan, and teammates' approval.

**Caveat:** New S3 storage doesn't migrate pictures previously saved on EB's local ephemeral disk. If old DB rows refer to local files, plan a separate migration or have the affected users re-upload; do not silently assume those objects exist in S3.
