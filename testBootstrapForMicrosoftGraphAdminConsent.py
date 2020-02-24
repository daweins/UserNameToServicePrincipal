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

import jwt


#from msal import PublicClientApplication # MSAL doesn't support the Powershell ClientId hack, so don't bother

# create a struct to hold the user & the sp's tokens for graph, management, etc. TODO - this should be decomposed out to a class
privUser = 'Initial Global Admin User'
privSP   = "Service Principal we create and elevate"
credList = {}
credList[privUser] = {}
credList[privSP] = {}






# TODO - factor out the backoff code - I hate copypasta code

curCloud = AZURE_PUBLIC_CLOUD
authorityBase   =  curCloud.endpoints.active_directory
managementURI   = curCloud.endpoints.resource_manager
graphURI        = "https://graph.microsoft.com/" # Don't see any endpoint in the cloud object - will work w/ PG to remove need for this hardcoding of Graph 2.0 endpoint. See https://docs.microsoft.com/en-us/azure/azure-government/documentation-government-developer-guIde for Gov endpoint
graphSPName     = 'https://graph.microsoft.com'



uriToAuthAgainstList = [graphURI]




# TODO - decide if this should be hardcoded, or left as a random GUId
appName = str(uuid.uuid4())

print("Starting. Note - we expect transient errors & retries - we are not waiting arbitrary times for AAD propagation")

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
    
    # keep track of errors to allow exponential backoff
    # TODO - decompose this out to something more reusable. It needs logging and periodic reseting to avoId near-infinite lockout
    backoff=1
    backoffRate = 2
    maxBackoff = 300


    # Create some useful strings for later
    #clientId    = "1b730954-1685-4b74-9bfd-dac224a7b894"       # Hardcoded Client Id for ADAL against RDFE - TODO - see if there is a better way to do this, but it"s a good cheat to get on the first rung of the ladder for now
    clientId    = "1950a258-227b-4e31-a9cf-717495945fc2"       # PowerShell Client Id for ADAL - TODO - see if there is a better way to do this, but it"s a good cheat to get on the first rung of the ladder for now
   
    authority   = authorityBase + "/" + tenantId
    app_url     = graphURI + "v1.0/applications"
    sp_url      = graphURI + "beta/servicePrincipals"
    me_url      = graphURI + "v1.0/me/"
    graphSP_url = graphURI + f"beta/serviceprincipals?$filter=servicePrincipalNames/any(n:n eq '{graphSPName}')"


    # Populate our token list for the privileged user. Use the known clientId to bootstrap our way in 
    for curAuthUri in uriToAuthAgainstList:
        gotToken = False
        while not gotToken:
            try:
                authContext = adal.AuthenticationContext(authority) 
                authResult = authContext.acquire_token_with_username_password(curAuthUri, userName, userPassword, clientId)  # Need to use ADAL - hardcoded Powershell ClientId trick doesn't work for MSAL
                if "accessToken" not in authResult:
                    print ("Didn't get an auth token for user {0} credentials for {1} Retrying with backoff".format(userName, curAuthUri))
                    time.sleep(backoff)
                    backoff *= backoffRate
                    # TODO - probably add some more logging, like the error result returned
                else:
                    token = authResult["accessToken"]
                    gotToken = True
                    print("Got user {0} token for {1} - adding it to our bag of headers!".format(userName, curAuthUri))
                    headers = {
                        "Authorization": "Bearer {}".format(token),
                        "Content-Type":"application/json"
                        }
                    credList[privUser][curAuthUri] = headers
            except Exception as e:
                print ("Didn't get an auth token for user {0} credentials for {1} Retrying with backoff".format(userName, curAuthUri))
                print (e)
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)

    # Get my principal Id, as I'll need it for assignment perms later
    meResponse = requests.get(me_url,headers=credList[privUser][graphURI])
    if meResponse.ok:
        meResponseJSON = json.loads(meResponse.content)
        privUserPrincipalId = meResponseJSON["id"]
        privUserUPN= meResponseJSON["userPrincipalName"]
    else:
        "Failed to get the priv user's Id"


    # Find the object ID of the Microsoft Graph Service Principal
    graphSPResponse = requests.get(graphSP_url, headers=credList[privUser][graphURI])
    graphSPResponseJSON = json.loads(graphSPResponse.content)
    graphSPObjId = graphSPResponseJSON["value"][0]["id"]

    # Create the application registration and get its Id
    gotAPPReg = False
    while not gotAPPReg:
        try:
            
            app_url     = graphURI + "v1.0/applications"
            # Adding magic role to resource Access - this is for Policy.Read.All (found by adding to an existing app reg in the portal, then viewing properties in Graph Explorer)
            appCreateContent = {
                "displayName" : appName#,
#                "requiredResourceAccess": [
 #               {
  #                  "resourceAppId": "00000003-0000-0000-c000-000000000000",
   #                 "resourceAccess": [
    #                    {
    #                        "id": "246dd0d5-5bd0-4def-940b-0421030a5b68",
     #                       "type": "Role"
      #                  }
       #             ]
 #               }
  #          ]
            }

            appResponse = requests.post(app_url, headers=credList[privUser][graphURI],data=json.dumps(appCreateContent))
            appResponseJSON = json.loads(appResponse.content)
            if "appId" not in appResponseJSON:
                print ("Failed to create the application registration. Retrying with backoff")
                print (appResponse.content)
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)
            else:
                appId    = appResponseJSON["appId"]
                appObjId = appResponseJSON["id"]
                print ("Created application registration with App Id:" + appId)
                gotAPPReg = True
        except Exception as e:
                print("Error creating application registration. Retrying with backoff")
                print (e)
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)
            
    # Wait to let AAD propagate
    # No more sleeping - retry logic now built in
    #print("Sleeping to allow AAD to propagate the new app registration")
    #time.sleep(10)


    # Create the service principal associated with the app registration we just created
    gotServicePrincipal = False
    while not gotServicePrincipal:
        try:
            servicePrincipalCreateContent = {
                "appId":appId
            }

        
            spResponse = requests.post(sp_url, headers=credList[privUser][graphURI], data=json.dumps(servicePrincipalCreateContent))
            spId = json.loads(spResponse.content)["id"]
            gotServicePrincipal = True
            print ("Newly created spId: " + spId)
        except Exception as e:
                print("Error creating the service principal. Retrying with backoff")
                print (e) 
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)


    # Create a password for the new app
    gotSPPwd = False
    while not gotSPPwd:
        try:
        
            
            appPwdCreateContent = {
                "passwordCredentials": [
                    {
                        "displayName" : "ATAT Generated Password"
                    }]
            }

            appPwdURL = graphURI + "/v1.0/applications/"+ appObjId + "/addPassword"
            appPwdResponse = requests.post(appPwdURL, headers=credList[privUser][graphURI], data=json.dumps(appPwdCreateContent) )
            appPwdJSON = json.loads(appPwdResponse.content)
            appPwd=appPwdJSON["secretText"]
            gotSPPwd = True

            print ("Created the app password")
        except Exception as e:
                print("Error creating the password for the service principal. Retrying with backoff")
                print (e)
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)



    # TODO - Loop this to iterate over an array of roles to assign 
    # Get the Company (Global) Admin role Id rather than relying on hardcoding
    # This doesn't need retry logic - use the hardcoded if it fails

    roleId = "794bb258-3e31-42ff-9ee4-731a72f62851" # no hardcoding
    try:
        roleListURL = graphURI + "/beta/roleManagement/directory/roleDefinitions"
        roleListResponse = requests.get(roleListURL,headers=credList[privUser][graphURI])
        roleListJSON = json.loads(roleListResponse.content)
        foundRole = False
        for curRole in roleListJSON["value"]:
            if curRole["displayName"] == "Company Administrator":
                print("Found Company (Global) Admin role: " + curRole["id"])
                roleId = curRole["id"]
                foundRole = True
        if not foundRole:
                print("Couldn't find the Company Admin Role - continuing with the hardcoded value of " + roleId)
    except  Exception as e:
        print("Error getting the Company (Global) Admin role - continuing with the hardcoded value of "+ roleId)
        print(e)


    # Add the app role assignment for our SP on the Microsoft.Graph API
    spAppRoleURL = f"https://graph.microsoft.com/beta/serviceprincipals/{graphSPObjId}/appRoleAssignedTo"
    spAppRoleContent =  {
            "appRoleId": "246dd0d5-5bd0-4def-940b-0421030a5b68", # Magic Role ID for Policy.Read.All
            "principalId": spId,
            "resourceId": graphSPObjId
        }

    spAppRoleResponse = requests.post(spAppRoleURL, headers=credList[privUser][graphURI], data=json.dumps(spAppRoleContent))
    spAppRoleJSON = json.loads(spAppRoleResponse.content)
    if spAppRoleResponse.ok:
        print("Added the Policy.Read.All perms to our Service Principal!")
    # TODO - check the response








   
# Test to make sure we can log in with this principal
backoff = 1

# Get tokens for the SP
for curAuthUri in uriToAuthAgainstList:
    gotSPAuth = False
    while not gotSPAuth:
        try:
            authContextSP = adal.AuthenticationContext(authority=authority)
            authResultSP = authContextSP.acquire_token_with_client_credentials(curAuthUri,appId,appPwd)
            if "accessToken" not in authResultSP:
                    print (f"Didn't get an auth token with the provIded user {0} credentials for {1}. Retrying with backoff".format(appId,curAuthUri))
                    time.sleep(backoff)
                    backoff *= backoffRate
                    # TODO - probably add some more logging, like the error result returned
            else:
                tokenSP = authResultSP["accessToken"]
                gotSPAuth = True
                print ("Got the token for the SP {0} for Uri {1}: {2}!".format(appId,curAuthUri,tokenSP))
                headersSP = {
                    "Authorization": "Bearer {}".format(tokenSP),
                    "Content-Type":"application/json"
                }
                credList[privSP][curAuthUri] = headersSP
            gotSPAuth = True
        except Exception as e:
            print ("Failure logging in with the new principal {0} for {1}. Don't be surprised if this takes 15-60 seconds.  Backing off".format(appId,curAuthUri))
            print (e)
            
            print ("Sleeping with backoff:" + str(backoff))
            time.sleep(backoff)
            backoff *= backoffRate
            if backoff > maxBackoff:
                print("Backed off too much - quitting with error (1)") 
                quit(1)


doConditionalAccessPolicyTestWithAdminConsentedSP = True
if doConditionalAccessPolicyTestWithAdminConsentedSP:
    
    curClientId = appId
    print (f"This will use clientID: {curClientId}.")
    time.sleep(60)
    app = ConfidentialClientApplication(curClientId,appPwd, authority=authority)
 #   app = ConfidentialClientApplication("f938905a-2750-4810-a59b-b68cf19ff44d","j?BAb9wQL5uFEu]N.MVjj_mCTugfPP30", authority=authority)
 
 
    capScopes = ["https://graph.microsoft.com/.default"]
    capToken = app.acquire_token_for_client(capScopes)["access_token"]
    capHeader = {
            "Authorization": "Bearer {}".format(capToken),
            "Content-Type":"application/json"
            }

    print("Now trying same creds against the policy endpoint")
    capURL = graphURI + "beta/conditionalAccess/policies"
    capResponse = requests.get(capURL,headers=capHeader)
    capJSON = json.loads(capResponse.content)
    print(f"Response of Graph 2.0 API query against {capURL} using ClientID {curClientId} : {capResponse.content}")





print("All Done!")
