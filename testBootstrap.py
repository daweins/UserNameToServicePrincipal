import adal
import requests
import json
import uuid
import time
import os
from msrestazure.azure_cloud import AZURE_PUBLIC_CLOUD # pip install azure
from msrestazure.azure_active_directory import AdalAuthentication

# TODO - move these to use the values from the msrestazure to support sovereign endpoints
authorityBase   =  AZURE_PUBLIC_CLOUD.endpoints.active_directory
graphURI        = "https://graph.microsoft.com"
redirectUri     = "urn:ietf:wg:oauth:2.0:oob"

# TODO - decide if this should be hardcoded, or left as a random GUID
appName = str(uuid.uuid4())

print("Starting")

#Tenant Information
currentDomain = os.environ.get("TENANTNAME") # ex: daweinsatat.onmicrosoft.com - note, because we append this to the userName, don't use the Tenant ID
userName      = os.environ.get("USERNAME")   # ex: bootstrapadmin if the email address was bootstrapadmin@daweinsatat.onmicrosoft.com
userPassword  = os.environ.get("USERPWD")    # ex: ImN0tPuttingAnExampleForThis! 


# Fail immediately if these aren't populated
if (currentDomain is None or userName is None or userPassword is None):
    print("Missing environment variables containing TENANTNAME, USERNAME, or USERPWD. Quitting with code 1 (error)")
    quit(1)
else:   
    print ("Environment variables with user parameters found")
    

   
    # Create some useful strings for later
    clientId    = "1b730954-1685-4b74-9bfd-dac224a7b894"      # PowerShell Client Id - TODO - see if there is a better way to do this, but it"s a good cheat to get on the first rung of the ladder for now
    authority   = authorityBase + "/" + currentDomain
    app_url     = graphURI + "/" + "/v1.0/applications"
    sp_url      = graphURI + "/" + "/beta/servicePrincipals"



    # Get our access token to the Graph endpoint. Use the known clientId to bootstrap our way in 
    try:
        userEmail = userName + '@' + currentDomain
        authContext = adal.AuthenticationContext(authority)
        authResult = authContext.acquire_token_with_username_password(graphURI, userEmail, userPassword, clientId) 
        if "accessToken" not in authResult:
            print ("Didn't get an auth token with the provided user credentials. Failing with 1 (error)")
            # TODO - probably add some more logging, like the error result returned
            quit(1)
        else:
            token = authResult["accessToken"]
            print("Got the token!")
    except Exception as e:
        print ("Error authenticating with the provided user credentials. Failing with 1 (error)")
        print e
        quit(1)


    # Create the application registration and get its ID
    try:
        headers = {
        "Authorization": "Bearer {}".format(token),
        "Content-Type":"application/json"
        }

        appCreateContent = {
            "displayName" : appName
        }

        appResponse = requests.post(app_url, headers=headers,data=json.dumps(appCreateContent))
        appResponseJSON = json.loads(appResponse.content)
        if "appId" not in appResponseJSON:
            print ("Failed to create the application registration. Failing with 1 (error)")
            quit(1)
        else:
            appId = appResponseJSON["appId"]
            print ("Created application registration with App ID:" + appId)
    except Exception as e:
            print("Error creating application registration. Failing with 1 (error)")
            print e
            quit(1)
        

    # Create the service principal associated with the app registration we just created
    try:
        servicePrincipalCreateContent = {
            "appId":appId
        }

        #TODO - setting the password looks to be a bear, but it needs to be done
        spResponse = requests.post(sp_url, headers=headers, data=json.dumps(servicePrincipalCreateContent))
        spId = json.loads(spResponse.content)["id"]

        print ("Newly created spId: " + spId)
    except Exception as e:
            print("Error creating the service principal. Failing with 1 (error)")
            print e
            quit(1)
    # TODO - This may or may not be necessary - tune as needed.
    #print ("Sleeping for AAD propogation")
    #time.sleep(5)

    # Create a password for the new service principal
    try:
        newPwd = str(uuid.uuid4())
        keyID = str(uuid.uuid4())
        
        # TODO - determine a timespan and set it accordingly. For this usecase, might want a very long life, or a rotation - I don't know
        spPwdCreateContent = {
            "passwordCredentials": [
                {
                    "startDateTime": "2020-01-01T23:54:15.295085Z", 
                    "endDateTime": "2025-01-23T23:54:15.295085Z", 
                    "keyId": keyID, 
                    "secretText": newPwd
                }]
        }

        spPwdURL = graphURI + "/beta/servicePrincipals/"+ spId
        spPwdResponse = requests.patch(spPwdURL, headers=headers, data=json.dumps(spPwdCreateContent) )
        if not spPwdResponse.ok:
            print "Failed to assign pwd. Failing with 1 (error)"
            quit(1)    
        print ("Created the service principal password")
    except Exception as e:
            print("Error creating the password for the service principal. Failing with 1 (error)")
            print e
            quit(1)


    # Get the Company (Global) Admin role ID rather than relying on hardcoding
    roleId = "794bb258-3e31-42ff-9ee4-731a72f62851" # Default - hard coded
    try:
        roleListURL = graphURI + "/beta/roleManagement/directory/roleDefinitions"
        roleListResponse = requests.get(roleListURL,headers=headers)
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


    roleAddContent = {
        "principalId": spId,
        "roleDefinitionId" : roleId,
        "resourceScope":"/"
    }

    role_url    = graphURI + "/beta/roleManagement/directory/roleAssignments" 
    roleCreateResponse = requests.post(role_url, headers=headers, data=json.dumps(roleAddContent))
    if not roleCreateResponse.ok:
        print "Failed to assign role. Failing with 1 (error)"
        quit(1)
    else:
        print ("Success! ")
        # TODO - probably shouldn't be printing out these creds, but this is a PoC
        print("appId:" + appId)
        print("SPID: " + spId)
        print("Password: " + newPwd)


# TEST code - log in with this principal
#time.sleep(30)
authContextTest = adal.AuthenticationContext(AZURE_PUBLIC_CLOUD.endpoints.active_directory+'/31132047-ce1c-4fd6-86f0-70e2aba8a28d')
spId='2d285550-7b74-47b6-bd22-daffe97a874b'
newPwd='1c16165a-2db4-4e36-8457-0fea73e01d78'
authContextTest.acquire_token_with_client_credentials(graphURI,spId,newPwd)
print("Success")