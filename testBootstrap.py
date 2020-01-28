import adal
import requests
import json
import uuid
import time
import os
import random
from msrestazure.azure_cloud import AZURE_PUBLIC_CLOUD # pip install azure
from msrestazure.azure_active_directory import AdalAuthentication
from msal import PublicClientApplication

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
graphURI        = "https://graph.microsoft.com/" # Don't see any endpoint in the cloud object - will work w/ PG to remove need for this hardcoding of Graph 2.0 endpoint. See https://docs.microsoft.com/en-us/azure/azure-government/documentation-government-developer-guide for Gov endpoint

uriToAuthAgainstList = [managementURI, graphURI]



# TODO - decide if this should be hardcoded, or left as a random GUID
appName = str(uuid.uuid4())

print("Starting. Note - we expect transient errors & retries - we are not waiting arbitrary times for AAD propagation")

#Tenant Information
tenantID      = os.environ.get("TENANTID") # ex: daweinsatat.onmicrosoft.com - note, because we append this to the userName, don't use the Tenant ID
userName      = os.environ.get("USERNAME")   # ex: bootstrapadmin if the email address was bootstrapadmin@daweinsatat.onmicrosoft.com
userPassword  = os.environ.get("USERPWD")    # ex: ImN0tPuttingAnExampleForThis! 

# Fail immediately if these aren't populated
if (tenantID is None or userName is None or userPassword is None):
    print("Missing environment variables containing TENANTID, USERNAME, or USERPWD. Quitting with code 1 (error)")
    quit(1)
else:   
    print ("Environment variables with user parameters found")
    
    # keep track of errors to allow exponential backoff
    # TODO - decompose this out to something more reusable. It needs logging and periodic reseting to avoid near-infinite lockout
    backoff=1
    backoffRate = 2
    maxBackoff = 300


    # Create some useful strings for later
    clientId    = "1b730954-1685-4b74-9bfd-dac224a7b894"      # PowerShell Client Id - TODO - see if there is a better way to do this, but it"s a good cheat to get on the first rung of the ladder for now
    authority   = authorityBase + "/" + tenantID
    app_url     = graphURI + "v1.0/applications"
    sp_url      = graphURI + "beta/servicePrincipals"



    # Populate our token list for the privileged user. Use the known clientId to bootstrap our way in 
    for curAuthUri in uriToAuthAgainstList:
        gotToken = False
        while not gotToken:
            try:
                
                authContext = adal.AuthenticationContext(authority)
                authResult = authContext.acquire_token_with_username_password(curAuthUri, userName, userPassword, clientId) 
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
            

            appCreateContent = {
                "displayName" : appName
            }

            appResponse = requests.post(app_url, headers=credList[privUser][graphURI],data=json.dumps(appCreateContent))
            appResponseJSON = json.loads(appResponse.content)
            if "appId" not in appResponseJSON:
                print ("Failed to create the application registration. Retrying with backoff")
                print appResponse.content
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

        
            spResponse = requests.post(sp_url, headers=credList[privUser][graphURI], data=json.dumps(servicePrincipalCreateContent))
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
            appPwdResponse = requests.post(appPwdURL, headers=credList[privUser][graphURI], data=json.dumps(appPwdCreateContent) )
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



    # TODO - Loop this to iterate over an array of roles to assign 
    # Get the Company (Global) Admin role ID rather than relying on hardcoding
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
            roleCreateResponse = requests.post(role_url, headers=credList[privUser][graphURI], data=json.dumps(roleAddContent))
            print roleCreateResponse.content
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
                print ("Successfully added role! ")
                print roleCreateResponse.content
                gotAssignedRole = True
                # TODO - probably shouldn't be printing out these creds, but this is a PoC

                # TODO - add a get role for the user as a check before declaring success
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
backoff = 1

# Get tokens for the SP
for curAuthUri in uriToAuthAgainstList:
    gotSPAuth = False
    while not gotSPAuth:
        try:
            authContextSP = adal.AuthenticationContext(authority=authority)
            authResultSP = authContextSP.acquire_token_with_client_credentials(curAuthUri,appId,appPwd)
            if "accessToken" not in authResultSP:
                    print ("Didn't get an auth token with the provided user {0} credentials for {1}}. Retrying with backoff".format(appId,curAuthUri))
                    time.sleep(backoff)
                    backoff *= backoffRate
                    # TODO - probably add some more logging, like the error result returned
            else:
                tokenSP = authResultSP["accessToken"]
                gotSPAuth = True
                print "Got the token for the SP {0} for Uri {1}: {2}!".format(appId,curAuthUri,tokenSP)
                headersSP = {
                    "Authorization": "Bearer {}".format(tokenSP),
                    "Content-Type":"application/json"
                }
                credList[privSP][curAuthUri] = headersSP
            gotSPAuth = True
        except Exception as e:
            print "Failure logging in with the new principal {0} for {1}. Don't be surprised if this takes 15-60 seconds.  Backing off".format(appId,curAuthUri)
            print e
            
            print ("Sleeping with backoff:" + str(backoff))
            time.sleep(backoff)
            backoff *= backoffRate
            if backoff > maxBackoff:
                print("Backed off too much - quitting with error (1)") 
                quit(1)


# TEST code - now do things with the principal
#
#

doAADSettingChangeTest = False

if doAADSettingChangeTest:
    #reset the backoff
    backoff = 1
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
            listSettingsURL  = graphURI  + "/beta/settings" #This is the hardcoded template for password settings
            changeSettingURL = graphURI  + "/beta/settings"

            print("Before: Current setting for password rules:")
            curSettingResponse = requests.get(listSettingsURL, headers=credList[privSP][graphURI] )
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
                    deleteResponse=requests.delete(deleteSettingURL, headers=credList[privSP][graphURI])
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
            newSettingResponse= requests.post(changeSettingURL, headers=credList[privSP][graphURI], data=json.dumps(testSetting))
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
            curSettingResponse = requests.get(listSettingsURL, headers=credList[privSP][graphURI] )
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
doManagementGroupTest = True
if doManagementGroupTest:


    #reset the backoff
    backoff = 1


    # Elevate Global Admin Users' privileges
    print ("Let's test using the new creds to create management groups")
   
    #Elevate the user to the root MG
    doneElevatingUserToMG = False
    while not doneElevatingUserToMG:
        try:
            elevateURL = managementURI +  'providers/Microsoft.Authorization/elevateAccess?api-version=2016-07-01'
            elevateResponse = requests.post(elevateURL, headers=credList[privUser][managementURI])
            print("Elevation Result: " + elevateResponse.content)
            if elevateResponse.ok:
                print "Successful elevation!"
                doneElevatingUserToMG = True
            else:
                print "Unsuccessful - trying again"
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)
        except Exception as e:
            print "Exception during elevation"
            print e
            print ("Sleeping with backoff:" + str(backoff))
            time.sleep(backoff)
            backoff *= backoffRate
            if backoff > maxBackoff:
                # TODO - normally this should set off alarms & logs & a longer sleep
                print("Backed off too much - quitting with error (1)") 
                quit(1)
  
    # Create the root group (note - can't even list the groups until the parent is in place). This needs to be done before elevating the perms
    # TODO - add logic to kill off any existing management groups - this is supposed to be a fresh test. Need to see if we can even reclean after creating the root MG...
    rootGroupName = "daweinsroot"

    doneCreateRootMG = False
    while not doneCreateRootMG:
        try:
            createRootURL = managementURI + "providers/Microsoft.Management/managementGroups/" + rootGroupName + "?api-version=2018-03-01-preview" #TODO - I need to learn python's format command 
            createRootMG =     {
            "id": "/providers/Microsoft.Management/managementGroups/ChildGroup",
            "type": "/providers/Microsoft.Management/managementGroups",
            "name": rootGroupName,
            "properties": {
                "tenantId": tenantID,
                "displayName": rootGroupName,
                "details": {
                "parent": {
                
                }
                }
            }
            }
            createRootMGResponse = requests.put(createRootURL, headers=credList[privUser][managementURI], data=json.dumps(createRootMG))
            print str(createRootMGResponse.content)
            if createRootMGResponse.ok:
                doneCreateRootMG = True
            else:
                print("Error creating root MG")
                print ("Sleeping with backoff:" + str(backoff))
                time.sleep(backoff)
                backoff *= backoffRate
                if backoff > maxBackoff:
                    # TODO - normally this should set off alarms & logs & a longer sleep
                    print("Backed off too much - quitting with error (1)") 
                    quit(1)
        except Exception as e:
            print("Exception creating root MG")
            print e
            print ("Sleeping with backoff:" + str(backoff))
            time.sleep(backoff)
            backoff *= backoffRate
            if backoff > maxBackoff:
                # TODO - normally this should set off alarms & logs & a longer sleep
                print("Backed off too much - quitting with error (1)") 
                quit(1)

  
    



print("All Done!")
