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

print("Starting. Note - we expect transient errors & retries - we are not waiting arbitrary times for AAD propagation")

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
    
    # keep track of errors to allow exponential backoff
    # TODO - decompose this out to something more reusable. It needs logging and periodic reseting to avoid near-infinite lockout
    backoff=1
    backoffRate = 2
    maxBackoff = 200


    # Create some useful strings for later
    clientId    = "1b730954-1685-4b74-9bfd-dac224a7b894"      # PowerShell Client Id - TODO - see if there is a better way to do this, but it"s a good cheat to get on the first rung of the ladder for now
    authority   = authorityBase + "/" + currentDomain
    app_url     = graphURI + "/" + "/v1.0/applications"
    sp_url      = graphURI + "/" + "/beta/servicePrincipals"



    # Get our access token to the Graph endpoint. Use the known clientId to bootstrap our way in 
    gotToken = False
    while not gotToken:
        try:
            userEmail = userName + '@' + currentDomain
            authContext = adal.AuthenticationContext(authority)
            authResult = authContext.acquire_token_with_username_password(graphURI, userEmail, userPassword, clientId) 
            if "accessToken" not in authResult:
                print ("Didn't get an auth token with the provided user credentials. Retrying with backoff")
                time.sleep(backoff)
                backoff *= backoffRate
                # TODO - probably add some more logging, like the error result returned
            else:
                token = authResult["accessToken"]
                gotToken = True
                print("Got the token!")
        except Exception as e:
            print ("Error authenticating with the provided user credentials. Retrying with backoff")
            print e
            print ("Sleeping with backoff:" + str(backoff))
            time.sleep(backoff)
            backoff *= backoffRate
            if backoff > maxBackoff:
                # TODO - normally this should set off alarms & logs & a longer sleep
                print("Backed off too much - quitting with error (1)") 
                quit(1)

    # Create the application registration and get its ID
    gotAPPReg = False
    while not gotAPPReg:
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
                print ("Failed to create the application registration. Retrying with backoff")
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
                print ("Created application registration with App ID:" + appId)
                gotAPPReg = True
        except Exception as e:
                print("Error creating application registration. Retrying with backoff")
                print e
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

        
            spResponse = requests.post(sp_url, headers=headers, data=json.dumps(servicePrincipalCreateContent))
            spId = json.loads(spResponse.content)["id"]
            gotServicePrincipal = True
            print ("Newly created spId: " + spId)
        except Exception as e:
                print("Error creating the service principal. Retrying with backoff")
                print e 
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
            appPwdResponse = requests.post(appPwdURL, headers=headers, data=json.dumps(appPwdCreateContent) )
            appPwdJSON = json.loads(appPwdResponse.content)
            appPwd=appPwdJSON["secretText"]
            gotSPPwd = True

            print ("Created the app password")
        except Exception as e:
                print("Error creating the password for the service principal. Retrying with backoff")
                print e 
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)



    # Get the Company (Global) Admin role ID rather than relying on hardcoding
    # This doesn't need retry logic - use the hardcoded if it fails
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



    # Assign the role to the SP
    gotAssignedRole = False
    while not gotAssignedRole:
        roleAddContent = {
            "principalId": spId,
            "roleDefinitionId" : roleId,
            "resourceScope":"/"
        }

        role_url    = graphURI + "/beta/roleManagement/directory/roleAssignments" 
        try:            
            roleCreateResponse = requests.post(role_url, headers=headers, data=json.dumps(roleAddContent))
            if not roleCreateResponse.ok:
                print "Failed to assign role. Retrying with backoff"    
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)
            else:
                # No more sleeping - retry logic build in
                #print ("Sleep for 15 secs to allow for propagation - the subsequent test fails without this")
                #time.sleep(15)
                print ("Success! ")
                gotAssignedRole = True
                # TODO - probably shouldn't be printing out these creds, but this is a PoC
                print("appId:" + appId)
                print("SPID: " + spId)
                print("Password: " + appPwd)
        except Exception as e:
                print ("Error assigning the role - retrying with backoff")
                print e
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)


# Test to make sure we can log in with this principal
gotSPAuth = False
while not gotSPAuth:
    try:
        authContextTest = adal.AuthenticationContext(AZURE_PUBLIC_CLOUD.endpoints.active_directory+'/31132047-ce1c-4fd6-86f0-70e2aba8a28d')
        authResultTest = authContextTest.acquire_token_with_client_credentials(graphURI,appId,appPwd)
        tokenTest = authResultTest["accessToken"]
        headersTest = {
            "Authorization": "Bearer {}".format(tokenTest),
            "Content-Type":"application/json"
            }
        print("Got Test Token:" + tokenTest)
        gotSPAuth = True
    except Exception as e:
        print ("Failure logging in with the new principal. Backing off")
        print e
        
        print ("Sleeping with backoff:" + str(backoff))
        time.sleep(backoff)
        backoff *= backoffRate
        if backoff > maxBackoff:
            # TODO - normally this should set off alarms & logs & a longer sleep
            print("Backed off too much - quitting with error (1)") 
            quit(1)


# TEST code - now do things with the principal
#
#

doAADSettingChangeTest = True
if doAADSettingChangeTest:
    print("Let's do something fun with it that requires very high privs, like altering password lockout period to something random!")

    gotSettings = False
    while not gotSettings:
        try:
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
            if curSettingResponse.ok:
                gotSettings = True
                print ("Got settings successfully")
            else:
                print ("Couldn't get settings - retrying with backoff")
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)
        except Exception as e:
            print("Error getting current settings for password rules - retrying with backoff")
            
            print ("Sleeping with backoff:" + str(backoff))
            time.sleep(backoff)
            backoff *= backoffRate
            if backoff > maxBackoff:
                # TODO - normally this should set off alarms & logs & a longer sleep
                print("Backed off too much - quitting with error (1)") 
                quit(1)

    # Delete any existing settings
    gotDeletedSetting = False
    while not gotDeletedSetting:       
        try: 
            for curSetting in curSettingsJSON["value"]:
                if curSetting["templateId"] == '5cf42378-d67d-4f36-ba46-e8b86229381d':
                    print( "Found existing setting with the same template: ")
                    deleteSettingURL = listSettingsURL + "/" + curSetting["id"]
                    deleteResponse=requests.delete(deleteSettingURL, headers=headersTest)
                    print("Delete Result: " + str(deleteResponse.ok))
                   # print("Sleeping to let the delete stick") - nope, no more sleeping due to retry logic
                    gotDeletedSetting = True
        except Exception as e:
                print("Error deleting the setting - retrying with backoff")
                
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)

    # Add the setting
    gotAddedSetting = False
    while not gotAddedSetting:
        try:            
            print("Altering the settings: lockout changing to " + str(newLockoutPeriod))
            newSettingResponse= requests.post(changeSettingURL, headers=headersTest, data=json.dumps(testSetting))
            if newSettingResponse.ok:
                print("Successful:" + str(newSettingResponse.ok))
                gotAddedSetting = True
            else:
                print("Error adding the new setting - retrying after backoff")
                print(newSettingResponse.content)
                
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)
            #print("Sleeping to let the new setting stick") - nope, no more sleeping due to retry logic
        except Exception as e:
            print("Error adding setting - retrying")
            
            print ("Sleeping with backoff:" + str(backoff))
            time.sleep(backoff)
            backoff *= backoffRate
            if backoff > maxBackoff:
                # TODO - normally this should set off alarms & logs & a longer sleep
                print("Backed off too much - quitting with error (1)") 
                quit(1)


    # Display the hopefully changed setting
    gotNewRules = False
    while not gotNewRules:
        try:
            print("After: Current setting for password rules:")
            curSettingResponse = requests.get(listSettingsURL, headers=headersTest )
            print(curSettingResponse.content)
            if curSettingResponse.ok:
                print "got new setting - manually eyeball that it exists"
                gotNewRules = True
            else:
                print "Error getting settings - backing off"
                
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)
        except Exception as e:
            print("Error getting settings")
            
            print ("Sleeping with backoff:" + str(backoff))
            time.sleep(backoff)
            backoff *= backoffRate
            if backoff > maxBackoff:
                # TODO - normally this should set off alarms & logs & a longer sleep
                print("Backed off too much - quitting with error (1)") 
                quit(1)

# Test creating a management group and granting the initial user perms to it
doManagementGroupTest = False
if doManagementGroupTest:
    # Elevate Global Admin Users' privileges
    print ("Let's test using the new creds to create management groups")
    #elevateURL = 'https://management.azure.com/providers/Microsoft.Authorization/elevateAccess?api-version=2016-07-01'
    #elevateResponse = requests.post(elevateURL, headers=headers)
    #print("Elevation Result: " + elevateResponse.content)

    # Create the root group (note - can't even list the groups until the parent is in place)
    # TODO - add logic to kill off any existing management groups - this is supposed to be a fresh test
    rootGroupName = "daweinsroot"

    createRootURL = "https://management.azure.com/providers/Microsoft.Management/managementGroups/" + rootGroupName + "?api-version=2018-03-01-preview" #TODO - I need to learn python's format command 
    createRootMG =     {
    "id": "/providers/Microsoft.Management/managementGroups/ChildGroup",
    "type": "/providers/Microsoft.Management/managementGroups",
    "name": rootGroupName,
    "properties": {
        "tenantId": "31132047-ce1c-4fd6-86f0-70e2aba8a28d",
        "displayName": rootGroupName,
        "details": {
        "parent": {
        
        }
        }
    }
    }
    createRootMGResponse = requests.put(createRootURL, headers=headers, data=json.dumps(createRootMG))
    print str(createRootMGResponse.ok)
    

print("All Done!")
