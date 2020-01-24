import adal
import requests
import json
import uuid
import time
import os
import random
from msrestazure.azure_cloud import AZURE_PUBLIC_CLOUD # pip install azure
from msrestazure.azure_active_directory import AdalAuthentication

# TODO - move these to use the values from the msrestazure to support sovereign endpoints
authorityBase   =  AZURE_PUBLIC_CLOUD.endpoints.active_directory
graphURI        = "https://graph.microsoft.com"

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
            appId    = appResponseJSON["appId"]
            appObjId = appResponseJSON["id"]
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

      
        spResponse = requests.post(sp_url, headers=headers, data=json.dumps(servicePrincipalCreateContent))
        spId = json.loads(spResponse.content)["id"]

        print ("Newly created spId: " + spId)
    except Exception as e:
            print("Error creating the service principal. Failing with 1 (error)")
            print e
            quit(1)


    # Create a password for the new app
    try:
       
        
        appPwdCreateContent = {
            "passwordCredentials": [
                {
                    "displayName" : "ATAT Generated Password"
                }]
        }

        appPwdURL = graphURI + "/v1.0/applications/"+ appObjId + "/addPassword"
        appPwdResponse = requests.post(appPwdURL, headers=headers, data=json.dumps(appPwdCreateContent) )
        appPwdJSON = json.loads(appPwdResponse.content)
        appPwd=appPwdJSON["secretText"]

        print ("Created the app password")
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
        print ("Sleep for a minute to allow for propagation - the subsequent test fails without this")
        time.sleep(60)
        print ("Success! ")
        # TODO - probably shouldn't be printing out these creds, but this is a PoC
        print("appId:" + appId)
        print("SPID: " + spId)
        print("Password: " + appPwd)


# TEST code - log in with this principal
#
#
#
#
#
# 
#
#
#
authContextTest = adal.AuthenticationContext(AZURE_PUBLIC_CLOUD.endpoints.active_directory+'/31132047-ce1c-4fd6-86f0-70e2aba8a28d')
authResultTest = authContextTest.acquire_token_with_client_credentials(graphURI,appId,appPwd)
tokenTest = authResultTest["accessToken"]
headersTest = {
    "Authorization": "Bearer {}".format(tokenTest),
    "Content-Type":"application/json"
    }
print("Got Test Token:" + tokenTest)
print("Let's do something fun with it that requires very high privs, like altering password lockout period to something random!")

newLockoutPeriod = str(random.randint(60,120))
testSetting = {
  "templateId": "5cf42378-d67d-4f36-ba46-e8b86229381d",
  "values": [
   {
            "name": "BannedPasswordCheckOnPremisesMode",
            "value": "Audit"
        },
        {
            "name": "EnableBannedPasswordCheckOnPremises",
            "value": "true"
        },
        {
            "name": "EnableBannedPasswordCheck",
            "value": "true"
        },
        {
            "name": "LockoutDurationInSeconds",
            "value": newLockoutPeriod
        },
        {
            "name": "LockoutThreshold",
            "value": "10"
        },
        {
            "name": "BannedPasswordList",
            "value": ""
        }
  ]
}
listSettingsURL = "https://graph.microsoft.com/beta/settings" #This is the hardcoded template for password settings
changeSettingURL = "https://graph.microsoft.com/beta/settings"

print("Before: Current setting for password rules:")
curSettingResponse = requests.get(listSettingsURL, headers=headersTest )
curSettingsJSON = json.loads(curSettingResponse.content)
print(curSettingResponse.content)

# Delete any existing settings
for curSetting in curSettingsJSON["value"]:
    if curSetting["templateId"] == '5cf42378-d67d-4f36-ba46-e8b86229381d':
        print( "Found existing setting with the same template: ")
        deleteSettingURL = listSettingsURL + "/" + curSetting["id"]
        deleteResponse=requests.delete(deleteSettingURL, headers=headersTest)
        print("Delete Result: " + str(deleteResponse.ok))
        print("Sleeping to let the delete stick")
        time.sleep(60)

# Add the setting
print("Altering the settings: lockout changing to " + str(newLockoutPeriod))
newSettingResponse= requests.post(changeSettingURL, headers=headersTest, data=json.dumps(testSetting))
print("Successful?:" + str(newSettingResponse.ok))
print("Sleeping to let the new setting stick")
time.sleep(60)


# Display the hopefully changed setting
print("After: Current setting for password rules:")
curSettingResponse = requests.get(listSettingsURL, headers=headersTest )
print(curSettingResponse.content)


print("Success!")
