import requests
import json
import uuid
import time
import os
import random
from msrestazure.azure_cloud import AZURE_PUBLIC_CLOUD # pip install azure
from cryptography.x509 import load_pem_x509_certificate
from cryptography.hazmat.backends import default_backend
from msal import ConfidentialClientApplication

tenantId      = os.environ.get("TENANTID") # ex: daweinsatat.onmicrosoft.com - note, because we append this to the userName, don't use the Tenant Id
userName      = os.environ.get("USERNAME")   # ex: bootstrapadmin if the email address was bootstrapadmin@daweinsatat.onmicrosoft.com
userPassword  = os.environ.get("USERPWD")    # ex: ImN0tPuttingAnExampleForThis! 
tenantName    = os.environ.get("TENANTNAME") # ex: bob.onmicrosoft.com

graphURI        = "https://graph.microsoft.com/" # Don't see any endpoint in the cloud object - will work w/ PG to remove need for this hardcoding of Graph 2.0 endpoint. See https://docs.microsoft.com/en-us/azure/azure-government/documentation-government-developer-guIde for Gov endpoint


print(f"Ready: got tenant: {tenantId}")

authority = f"https://login.microsoftonline.com/{tenantId}"
clientID = '0cd93960-f119-4810-b13b-a25dffaef555'
clientSecret = ""
app = ConfidentialClientApplication(clientID, authority=authority, client_credential=clientSecret)

scope = ["https://graph.microsoft.com/.default"]

# The pattern to acquire a token looks like this.
result = None

# First, the code looks up a token from the cache.
# Because we're looking for a token for the current app, not for a user,
# use None for the account parameter.
result = app.acquire_token_silent(scope, account=None)

if not result:
    print("No suitable token exists in cache. Let's get a new one from AAD.")
    result = app.acquire_token_for_client(scopes=scope)

if "access_token" in result:
    # Call a protected API with the access token.
    curToken = result["access_token"]
    print(curToken)
    endpoint =  graphURI + "beta/conditionalAccess/policies"
 #   endpoint =  graphURI + "v1.0/users"
    http_headers = {'Authorization': 'Bearer ' + curToken,
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'}
    data = requests.get(endpoint, headers=http_headers, stream=False).json()
    print(data)

else:
    print(result.get("error"))
    print(result.get("error_description"))
    print(result.get("correlation_id"))  # You might need this when reporting a bug.





