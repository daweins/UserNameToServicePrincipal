import adal
import requests
import json
import uuid
import time
import os
import random
from msrestazure.azure_cloud import AZURE_PUBLIC_CLOUD # pip install azure
from msrestazure.azure_active_directory import AdalAuthentication
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend
from msal import ConfidentialClientApplication
from msal import PublicClientApplication
import msal
import jwt

curCloud = AZURE_PUBLIC_CLOUD
authorityBase   =  curCloud.endpoints.active_directory
graphURI        = "https://graph.microsoft.com/" # Don't see any endpoint in the cloud object - will work w/ PG to remove need for this hardcoding of Graph 2.0 endpoint. See https://docs.microsoft.com/en-us/azure/azure-government/documentation-government-developer-guIde for Gov endpoint

#Tenant Information
tenantId      = os.environ.get("TENANTID") # ex: daweinsatat.onmicrosoft.com - note, because we append this to the userName, don't use the Tenant Id
userName      = os.environ.get("USERNAME")   # ex: bootstrapadmin if the email address was bootstrapadmin@daweinsatat.onmicrosoft.com
userPassword  = os.environ.get("USERPWD")    # ex: ImN0tPuttingAnExampleForThis! 
tenantName    = os.environ.get("TENANTNAME") # ex: bob.onmicrosoft.com

# Fail immediately if these aren't populated
if (tenantId is None or userName is None or userPassword is None):
    print("Missing environment variables containing TENANTID, USERNAME, or USERPWD. Quitting with code 1 (error)")
    quit(1)
else:   
    print ("Environment variables with user parameters found")
    

    # Create some useful strings for later
    #clientId    = "1b730954-1685-4b74-9bfd-dac224a7b894"       # Hardcoded Client Id for ADAL against RDFE - TODO - see if there is a better way to do this, but it's a good cheat to get on the first rung of the ladder for now
    clientId    = "1950a258-227b-4e31-a9cf-717495945fc2"       # PowerShell Client Id for ADAL - TODO - see if there is a better way to do this, but it"s a good cheat to get on the first rung of the ladder for now
 
    # Note - 1PP don't work: https://identitydocs.azurewebsites.net/static/aad/preauthorization.html


    #clientId = '4f570b28-3401-4e20-b01d-dc517f2949f4' #sample known clientID prepopulated that has a SP
    #clientId = '8cd8dbae-abd9-4c0b-91a8-9d4604facd52' # sample known clientID prepopulated with no SP
    #clientId = 'b1b71e9b-6abd-45d1-bf61-127e287d6a50'
    authority   = authorityBase + "/" + tenantId
    #authority   = authorityBase + "/organizations"


    try:
        # Following example from https://docs.microsoft.com/en-us/azure/active-directory/develop/scenario-desktop-acquire-token?tabs=python#username-and-password
        app = msal.PublicClientApplication(clientId, authority=authority)
        #graphScopes = ["https://graph.microsoft.com/.default"]
        graphScopes = ["User.ReadBasic.All"]

        authResult = app.acquire_token_by_username_password(userName, userPassword, graphScopes)
        if "accessToken" not in authResult:
            print (f"Didn't get an auth token for user {userName} credentials")
            print (authResult.error_description)
        else:
            token = authResult["accessToken"]
            gotToken = True
            print(f"Got user {userName} token:  {token}")
    except Exception as e:
        print ("Didn't get an auth token for user {0} credentials for {1}")
        print (e)