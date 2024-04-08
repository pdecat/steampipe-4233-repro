```
export STEAMPIPE_DATABASE_PORT=59193
export STEAMPIPE_INSTALL_DIR=$(pwd)/.steampipe
mkdir -p $STEAMPIPE_INSTALL_DIR/config/
cat <<EOF > $STEAMPIPE_INSTALL_DIR/config/default.spc
options "database" {
   port   = $STEAMPIPE_DATABASE_PORT
   listen = "127.0.0.1"
}
EOF
cat <<EOF > $STEAMPIPE_INSTALL_DIR/config/aws-plugin.spc
plugin "aws" {
  source = "aws@latest"

  # Not documented
  # https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cloudfront-limits.html
  limiter "aws_cloudfront" {
    max_concurrency = 10
    bucket_size     = 10
    fill_rate       = 5

    scope  = ["connection", "service"]
    where  = "service = 'cloudfront'"
  }
}
EOF
export AWS_PROFILE=my-profile
steampipe plugin install aws

rm .steampipe/config/aws_*
steampipe service start --database-listen localhost

poetry run python steampipe_4233_repro/__init__.py 012345678901
```
