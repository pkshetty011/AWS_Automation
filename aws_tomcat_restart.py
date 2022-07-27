import boto3
import time
import json
import logging
import re
import pycurl, validators

# Get Tenent Url from Keeper tenents List and Validate for Successful Responce
error_flag=False
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
filename = 'local path for keeper file'

# AWS connection
ec2client = boto3.resource('ec2', region_name="us-east-2")
ssm_client = boto3.client('ssm', region_name="us-east-2")

# Get information for all running instances
running_instances = ec2client.instances.filter(Filters=[{
    'Name': 'instance-state-name', 
    'Values': ['running'],
    'Name': 'tag:Environment',
    'Values': ['poc01','poc05']}])

def get_instance_id(tenant_info,running_instances):
    ip_string = tenant_info['custom_fields']['APPSERVER']
    appserver_ip = re.findall( r'[0-9]+(?:\.[0-9]+){3}', ip_string )[0]
    for instance in running_instances:
        if instance.private_ip_address == appserver_ip:
            newinstanceId = instance.id
            return newinstanceId

def url_exists(url):
    # Check if the given URL exists
    if validators.url(url):
        c = pycurl.Curl()
        c.setopt(pycurl.NOBODY, True)
        c.setopt(pycurl.FOLLOWLOCATION, False)
        c.setopt(pycurl.CONNECTTIMEOUT, 10)
        c.setopt(pycurl.TIMEOUT, 100)
        c.setopt(pycurl.COOKIEFILE, '')
        c.setopt(pycurl.URL, url)
        try:
            c.perform()
            response_code = c.getinfo(pycurl.RESPONSE_CODE)
            c.close()
            return True if response_code < 400 else False
        except pycurl.error as err:
            errstr = err
            raise OSError('An error occurred: {}'.format(errstr))
    else:
        raise ValueError('"{}" is not a valid url'.format(url))

def get_local_json_data(filename):
    try:
        fp=open(filename,"r")
    except:
        logger.warning(f"Local tenant json file does not exists {filename}")
        return error_flag
    try:
        data=json.load(fp)
        return data
    except Exception as e:
        logger.warning("Not able to load json ")
        logger.warning("Exception",exc_info=True)
        return error_flag

def restart_tenant(tenant_info):
    tenant_name = tenant_info['custom_fields']['TenantID'] 
    newinstanceId = get_instance_id(tenant_info,running_instances)
    cmd = """
    sudo su
    su - {tenant_name} -c "sh /path/startup.sh"
    """.format(tenant_name=tenant_name)
    try:
        response = ssm_client.send_command(
        InstanceIds=[newinstanceId],
        DocumentName="AWS-RunShellScript",
        Parameters={'commands': [cmd]}, 
        )
        command_id = response['Command']['CommandId']
        time.sleep(3)
        output = ssm_client.get_command_invocation(
           CommandId=command_id,
           InstanceId=newinstanceId,
                )
        logging.info(output)
    except Exception as e:
        print("Inside except",e)


# Get all the tenant detail from keepr once a day
tenant_info_data = get_local_json_data(filename)
selected_tenant_info = tenant_info_data['records']
poc_voult = []
for i in selected_tenant_info:
    if i['folders'][0]['shared_folder'] == "Voult_Folder":
        poc_voult.append(i)

if __name__ == "__main__":
    for tenant_info in poc_voult:
        if 'login_url' in tenant_info and 'custom_fields' in tenant_info:
            if tenant_info['custom_fields']['POD'].startswith("poc"):
                login_url = tenant_info['login_url'] 
                try:   
                    response = url_exists(login_url)
                    if response == True:
                        logger.info("Successful")
                    else:
                        restart_tenant(tenant_info)
                        logger.warning("Failed to retrieve")
                except Exception as e:
                    restart_tenant(tenant_info)
                    logger.warning("Failed to retrieve")
