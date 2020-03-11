# UserNameToServicePrincipal
Azure python PoC to demonstrate creating a service principal with elevated permissions given an Azure Tenant with the credentials for a Global Admin User. 

Currently uses a hard-coded clientID impersonating PowerShell that likely only works in ADAL (not MSAL) - this approach is being still being evaluated by MSFT's Identity team

Now with some sample code showing manipulating AAD settings as well as populating the initial management group in a new tenant


testBootstrapForMicrosoftGraphAdminConsent.py demonstrates the ability to escalate permissions required for Microsoft Graph API endpoints requiring admin consent. The initial authentication using the hardcoded "Powershell" clientID should likely be moved to Azure CLI
