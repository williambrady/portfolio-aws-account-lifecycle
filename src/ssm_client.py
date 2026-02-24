import sys

import boto3


def get_session(profile_name=None, role_arn=None, region_name=None, session_name="account-lifecycle"):
    if profile_name:
        return boto3.Session(profile_name=profile_name, region_name=region_name)
    if role_arn:
        sts = boto3.client("sts", region_name=region_name)
        response = sts.assume_role(RoleArn=role_arn, RoleSessionName=session_name)
        credentials = response["Credentials"]
        return boto3.Session(
            aws_access_key_id=credentials["AccessKeyId"],
            aws_secret_access_key=credentials["SecretAccessKey"],
            aws_session_token=credentials["SessionToken"],
            region_name=region_name,
        )
    return boto3.Session(region_name=region_name)


def read_unique_number(session, parameter_path):
    ssm = session.client("ssm")
    try:
        response = ssm.get_parameter(Name=parameter_path)
        return int(response["Parameter"]["Value"])
    except ssm.exceptions.ParameterNotFound:
        print(f"ERROR: SSM parameter not found: {parameter_path}", file=sys.stderr)
        sys.exit(1)
    except ValueError:
        print(f"ERROR: SSM parameter is not a valid integer: {parameter_path}", file=sys.stderr)
        sys.exit(1)


def increment_unique_number(session, parameter_path, current_value):
    ssm = session.client("ssm")
    new_value = current_value + 1
    ssm.put_parameter(
        Name=parameter_path,
        Value=str(new_value),
        Type="String",
        Overwrite=True,
    )
    print(f"SSM unique number incremented: {current_value} -> {new_value}", file=sys.stderr)
    return new_value
