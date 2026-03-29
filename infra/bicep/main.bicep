// ============================================================================
// Clinical Decision Support System (CDSS) - Azure Infrastructure
// Agentic RAG Architecture on Azure
// ============================================================================

// === PARAMETERS ===

@description('The Azure region for all resources')
param location string = resourceGroup().location

@description('Environment name')
@allowed([
  'dev'
  'staging'
  'prod'
])
param environment string = 'dev'

@description('Expose production API publicly. false keeps the Container Apps environment internal-only.')
param prodPublicApi bool = false

@description('Project name prefix for resource naming')
param projectName string = 'cdss'

@description('Container image for the FastAPI application')
param containerImage string = 'cdssacr.azurecr.io/cdss-api:latest'

@description('Enable managed-identity based private Azure Container Registry (ACR) image pulls.')
param acrUseManagedIdentity bool = false

@description('Create ACR in this resource group when acrUseManagedIdentity=true.')
param acrCreate bool = false

@description('ACR name (without domain), required when acrUseManagedIdentity=true. Example: myacr')
param acrName string = ''

@description('ACR SKU to use when acrCreate=true.')
@allowed([
  'Basic'
  'Standard'
  'Premium'
])
param acrSku string = 'Standard'

@description('Azure OpenAI GPT-4o model deployment name')
param gpt4oDeploymentName string = 'gpt-4o'

@description('Azure OpenAI GPT-4o-mini model deployment name')
param gpt4oMiniDeploymentName string = 'gpt-4o-mini'

@description('Azure OpenAI text-embedding-3-large deployment name')
param embeddingDeploymentName string = 'text-embedding-3-large'

@description('Azure OpenAI GPT-4o deployment capacity (in thousands TPM units)')
@minValue(1)
param gpt4oCapacity int = environment == 'prod' ? 80 : 20

@description('Azure OpenAI GPT-4o-mini deployment capacity (in thousands TPM units)')
@minValue(1)
param gpt4oMiniCapacity int = environment == 'prod' ? 120 : 40

@description('Azure OpenAI embedding deployment capacity (in thousands TPM units)')
@minValue(1)
param embeddingCapacity int = environment == 'prod' ? 120 : 40

@description('Set to true to restore a soft-deleted Azure OpenAI account with the same name')
param openaiRestore bool = false

@description('Set to true to restore a soft-deleted Document Intelligence account with the same name')
param docIntelRestore bool = false

@description('Cosmos DB database name')
param cosmosDatabaseName string = 'cdss-db'

@description('Allowed CORS origins for the backend API.')
param corsAllowedOrigins array = [
  'http://localhost:3000'
  'http://localhost:3001'
]

@description('Enable Azure Entra ID JWT authentication middleware in the API.')
param authEnabled bool = environment == 'prod'

@description('Expected JWT audience for API bearer tokens (Application ID URI / client ID).')
param authAudience string = ''

@description('Optional required scopes for API access.')
param authRequiredScopes array = []

@description('Tags to apply to all resources')
param tags object = {
  project: 'cdss-agentic-rag'
  environment: environment
  managedBy: 'bicep'
}

// === VARIABLES ===

var uniqueSuffix = uniqueString(resourceGroup().id)
var resourcePrefix = '${projectName}-${environment}'
var resourcePrefixClean = replace('${projectName}${environment}', '-', '')
var acrGeneratedName = toLower(take('${resourcePrefixClean}acr${uniqueSuffix}', 50))
var acrEffectiveName = !empty(acrName) ? toLower(acrName) : acrGeneratedName
var acrLoginServer = '${acrEffectiveName}.azurecr.io'

// Networking
var vnetName = '${resourcePrefix}-vnet'
var vnetAddressPrefix = '10.0.0.0/16'
var appSubnetName = 'app-subnet'
var appSubnetPrefix = '10.0.1.0/24'
var dataSubnetName = 'data-subnet'
var dataSubnetPrefix = '10.0.2.0/24'
var aiSubnetName = 'ai-subnet'
var aiSubnetPrefix = '10.0.3.0/24'
var integrationSubnetName = 'integration-subnet'
var integrationSubnetPrefix = '10.0.4.0/24'
var containerAppEnvironmentInternal = environment == 'prod' && !prodPublicApi
var apiExposureMode = environment == 'prod' ? (prodPublicApi ? 'public' : 'private') : 'public'

// Resource names
var managedIdentityName = '${resourcePrefix}-identity'
var keyVaultName = '${resourcePrefixClean}kv${uniqueSuffix}'
var logAnalyticsName = '${resourcePrefix}-logs'
var appInsightsName = '${resourcePrefix}-insights'
var containerAppEnvName = '${resourcePrefix}-cae'
var containerAppName = '${resourcePrefix}-api'
var staticWebAppName = '${resourcePrefix}-frontend'
var openaiName = '${resourcePrefixClean}oai${uniqueSuffix}'
var aiSearchName = '${resourcePrefix}-search-${uniqueSuffix}'
var docIntelligenceName = '${resourcePrefix}-docintel-${uniqueSuffix}'
var cosmosAccountName = '${resourcePrefixClean}cosmos${uniqueSuffix}'
var storageAccountName = '${resourcePrefixClean}st${uniqueSuffix}'
var redisName = '${resourcePrefix}-redis-${uniqueSuffix}'

// ============================================================================
// NETWORKING
// ============================================================================

// --- Network Security Groups ---

resource appNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${appSubnetName}-nsg'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowHTTPS'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AllowHTTP'
        properties: {
          priority: 110
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '80'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'AllowHealthProbes'
        properties: {
          priority: 120
          direction: 'Inbound'
          access: 'Allow'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: 'AzureLoadBalancer'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource dataNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${dataSubnetName}-nsg'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowAppSubnet'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: appSubnetPrefix
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'DenyDirectInternet'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource aiNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${aiSubnetName}-nsg'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowAppSubnet'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '443'
          sourceAddressPrefix: appSubnetPrefix
          destinationAddressPrefix: '*'
        }
      }
      {
        name: 'DenyDirectInternet'
        properties: {
          priority: 4096
          direction: 'Inbound'
          access: 'Deny'
          protocol: '*'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: 'Internet'
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

resource integrationNsg 'Microsoft.Network/networkSecurityGroups@2023-11-01' = {
  name: '${integrationSubnetName}-nsg'
  location: location
  tags: tags
  properties: {
    securityRules: [
      {
        name: 'AllowAppSubnet'
        properties: {
          priority: 100
          direction: 'Inbound'
          access: 'Allow'
          protocol: 'Tcp'
          sourcePortRange: '*'
          destinationPortRange: '*'
          sourceAddressPrefix: appSubnetPrefix
          destinationAddressPrefix: '*'
        }
      }
    ]
  }
}

// --- Virtual Network ---

resource vnet 'Microsoft.Network/virtualNetworks@2023-11-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        vnetAddressPrefix
      ]
    }
    subnets: [
      {
        name: appSubnetName
        properties: {
          addressPrefix: appSubnetPrefix
          networkSecurityGroup: {
            id: appNsg.id
          }
          serviceEndpoints: [
            {
              service: 'Microsoft.Storage'
            }
            {
              service: 'Microsoft.KeyVault'
            }
          ]
          delegations: [
            {
              name: 'Microsoft.App.environments'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: dataSubnetName
        properties: {
          addressPrefix: dataSubnetPrefix
          networkSecurityGroup: {
            id: dataNsg.id
          }
          serviceEndpoints: [
            {
              service: 'Microsoft.Storage'
            }
            {
              service: 'Microsoft.KeyVault'
            }
          ]
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: aiSubnetName
        properties: {
          addressPrefix: aiSubnetPrefix
          networkSecurityGroup: {
            id: aiNsg.id
          }
          serviceEndpoints: [
            {
              service: 'Microsoft.Storage'
            }
            {
              service: 'Microsoft.KeyVault'
            }
          ]
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
      {
        name: integrationSubnetName
        properties: {
          addressPrefix: integrationSubnetPrefix
          networkSecurityGroup: {
            id: integrationNsg.id
          }
          serviceEndpoints: [
            {
              service: 'Microsoft.Storage'
            }
            {
              service: 'Microsoft.KeyVault'
            }
          ]
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

// --- Private DNS Zones ---

resource cosmosPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.documents.azure.com'
  location: 'global'
  tags: tags
}

resource cosmosPrivateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: cosmosPrivateDnsZone
  name: '${vnetName}-cosmos-link'
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource searchPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.search.windows.net'
  location: 'global'
  tags: tags
}

resource searchPrivateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: searchPrivateDnsZone
  name: '${vnetName}-search-link'
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource keyVaultPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: tags
}

resource keyVaultPrivateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: keyVaultPrivateDnsZone
  name: '${vnetName}-keyvault-link'
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource openaiPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.openai.azure.com'
  location: 'global'
  tags: tags
}

resource openaiPrivateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: openaiPrivateDnsZone
  name: '${vnetName}-openai-link'
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

resource cognitivePrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = {
  name: 'privatelink.cognitiveservices.azure.com'
  location: 'global'
  tags: tags
}

resource cognitivePrivateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = {
  parent: cognitivePrivateDnsZone
  name: '${vnetName}-cognitiveservices-link'
  location: 'global'
  properties: {
    virtualNetwork: {
      id: vnet.id
    }
    registrationEnabled: false
  }
}

// ============================================================================
// SECURITY - Managed Identity
// ============================================================================

resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: managedIdentityName
  location: location
  tags: tags
}

// ============================================================================
// MONITORING
// ============================================================================

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: environment == 'prod' ? 90 : 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    workspaceCapping: {
      dailyQuotaGb: environment == 'prod' ? 10 : 1
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
    RetentionInDays: environment == 'prod' ? 90 : 30
  }
}

// ============================================================================
// AI SERVICES
// ============================================================================

// --- Azure OpenAI ---

resource openai 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: openaiName
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: union({
    customSubDomainName: openaiName
    publicNetworkAccess: environment == 'prod' ? 'Disabled' : 'Enabled'
    networkAcls: {
      defaultAction: environment == 'prod' ? 'Deny' : 'Allow'
    }
  }, openaiRestore ? {
    restore: true
  } : {})
}

resource gpt4oDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openai
  name: gpt4oDeploymentName
  sku: {
    name: 'Standard'
    capacity: gpt4oCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o'
      version: '2024-08-06'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

resource gpt4oMiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openai
  name: gpt4oMiniDeploymentName
  dependsOn: [
    gpt4oDeployment
  ]
  sku: {
    name: 'Standard'
    capacity: gpt4oMiniCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-4o-mini'
      version: '2024-07-18'
    }
    raiPolicyName: 'Microsoft.DefaultV2'
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-04-01-preview' = {
  parent: openai
  name: embeddingDeploymentName
  dependsOn: [
    gpt4oMiniDeployment
  ]
  sku: {
    name: 'Standard'
    capacity: embeddingCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: '1'
    }
  }
}

// --- Azure AI Search ---

resource aiSearch 'Microsoft.Search/searchServices@2024-03-01-preview' = {
  name: aiSearchName
  location: location
  tags: tags
  sku: {
    name: environment == 'prod' ? 'standard2' : 'standard'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hostingMode: 'default'
    partitionCount: environment == 'prod' ? 2 : 1
    replicaCount: environment == 'prod' ? 3 : 1
    publicNetworkAccess: environment == 'prod' ? 'disabled' : 'enabled'
    semanticSearch: 'standard'
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
  }
}

// --- Azure Document Intelligence ---

resource documentIntelligence 'Microsoft.CognitiveServices/accounts@2024-04-01-preview' = {
  name: docIntelligenceName
  location: location
  tags: tags
  kind: 'FormRecognizer'
  sku: {
    name: environment == 'prod' ? 'S0' : 'S0'
  }
  properties: union({
    customSubDomainName: docIntelligenceName
    publicNetworkAccess: environment == 'prod' ? 'Disabled' : 'Enabled'
    networkAcls: {
      defaultAction: environment == 'prod' ? 'Deny' : 'Allow'
    }
  }, docIntelRestore ? {
    restore: true
  } : {})
}

// ============================================================================
// DATA SERVICES
// ============================================================================

// --- Cosmos DB ---

resource cosmosAccount 'Microsoft.DocumentDB/databaseAccounts@2024-05-15' = {
  name: cosmosAccountName
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
      maxStalenessPrefix: 100
      maxIntervalInSeconds: 5
    }
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false // Disabled due to capacity constraints in East US 2
      }
    ]
    capabilities: [
      {
        name: 'EnableNoSQLVectorSearch'
      }
      {
        name: 'EnableServerless'
      }
    ]
    publicNetworkAccess: environment == 'prod' ? 'Disabled' : 'Enabled'
    enableAutomaticFailover: environment == 'prod'
    enableMultipleWriteLocations: false
    isVirtualNetworkFilterEnabled: environment == 'prod'
    backupPolicy: {
      type: 'Periodic'
      periodicModeProperties: {
        backupIntervalInMinutes: environment == 'prod' ? 60 : 240
        backupRetentionIntervalInHours: environment == 'prod' ? 720 : 168
        backupStorageRedundancy: environment == 'prod' ? 'Geo' : 'Local'
      }
    }
  }
}

resource cosmosDatabase 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-05-15' = {
  parent: cosmosAccount
  name: cosmosDatabaseName
  properties: {
    resource: {
      id: cosmosDatabaseName
    }
  }
}

// Container: patient-profiles
resource patientProfilesContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name: 'patient-profiles'
  properties: {
    resource: {
      id: 'patient-profiles'
      partitionKey: {
        paths: [
          '/patient_id'
        ]
        kind: 'Hash'
        version: 2
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/"_etag"/?'
          }
          {
            path: '/content_vector/*'
          }
        ]
        compositeIndexes: [
          [
            {
              path: '/patient_id'
              order: 'ascending'
            }
            {
              path: '/updated_at'
              order: 'descending'
            }
          ]
        ]
      }
      defaultTtl: -1
      uniqueKeyPolicy: {
        uniqueKeys: [
          {
            paths: [
              '/patient_id'
              '/profile_version'
            ]
          }
        ]
      }
    }
  }
}

// Container: conversation-history
resource conversationHistoryContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name: 'conversation-history'
  properties: {
    resource: {
      id: 'conversation-history'
      partitionKey: {
        paths: [
          '/session_id'
        ]
        kind: 'Hash'
        version: 2
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/"_etag"/?'
          }
        ]
        compositeIndexes: [
          [
            {
              path: '/session_id'
              order: 'ascending'
            }
            {
              path: '/timestamp'
              order: 'descending'
            }
          ]
        ]
      }
      defaultTtl: 2592000 // 30 days
    }
  }
}

// Container: embedding-cache (with vector search policy)
resource embeddingCacheContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name: 'embedding-cache'
  properties: {
    resource: {
      id: 'embedding-cache'
      partitionKey: {
        paths: [
          '/document_id'
        ]
        kind: 'Hash'
        version: 2
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/"_etag"/?'
          }
          {
            path: '/content_vector/*'
          }
        ]
        vectorIndexes: [
          {
            path: '/content_vector'
            type: 'diskANN'
          }
        ]
      }
      vectorEmbeddingPolicy: {
        vectorEmbeddings: [
          {
            path: '/content_vector'
            dataType: 'float32'
            dimensions: 3072
            distanceFunction: 'cosine'
          }
        ]
      }
      defaultTtl: -1
    }
  }
}

// Container: audit-log
resource auditLogContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name: 'audit-log'
  properties: {
    resource: {
      id: 'audit-log'
      partitionKey: {
        paths: [
          '/user_id'
        ]
        kind: 'Hash'
        version: 2
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/"_etag"/?'
          }
        ]
        compositeIndexes: [
          [
            {
              path: '/user_id'
              order: 'ascending'
            }
            {
              path: '/timestamp'
              order: 'descending'
            }
          ]
          [
            {
              path: '/action'
              order: 'ascending'
            }
            {
              path: '/timestamp'
              order: 'descending'
            }
          ]
        ]
      }
      defaultTtl: environment == 'prod' ? 31536000 : 7776000 // 1 year prod, 90 days non-prod
    }
  }
}

// Container: agent-state
resource agentStateContainer 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-05-15' = {
  parent: cosmosDatabase
  name: 'agent-state'
  properties: {
    resource: {
      id: 'agent-state'
      partitionKey: {
        paths: [
          '/session_id'
        ]
        kind: 'Hash'
        version: 2
      }
      indexingPolicy: {
        indexingMode: 'consistent'
        automatic: true
        includedPaths: [
          {
            path: '/*'
          }
        ]
        excludedPaths: [
          {
            path: '/"_etag"/?'
          }
          {
            path: '/state_vector/*'
          }
        ]
      }
      defaultTtl: 86400 // 24 hours
    }
  }
}

// --- Blob Storage ---

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  tags: tags
  sku: {
    name: environment == 'prod' ? 'Standard_GRS' : 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: true
    networkAcls: {
      defaultAction: environment == 'prod' ? 'Deny' : 'Allow'
      bypass: 'AzureServices'
      virtualNetworkRules: environment == 'prod' ? [
        {
          id: '${vnet.id}/subnets/${appSubnetName}'
          action: 'Allow'
        }
      ] : []
    }
    encryption: {
      services: {
        blob: {
          enabled: true
          keyType: 'Account'
        }
      }
      keySource: 'Microsoft.Storage'
    }
  }
}

resource blobServices 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 30
    }
    containerDeleteRetentionPolicy: {
      enabled: true
      days: 30
    }
  }
}

resource stagingDocumentsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobServices
  name: 'staging-documents'
  properties: {
    publicAccess: 'None'
    metadata: {
      purpose: 'Raw documents uploaded for processing'
    }
  }
}

resource protocolsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobServices
  name: 'treatment-protocols'
  properties: {
    publicAccess: 'None'
    metadata: {
      purpose: 'Treatment protocol PDFs'
    }
  }
}

resource processedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobServices
  name: 'processed-documents'
  properties: {
    publicAccess: 'None'
    metadata: {
      purpose: 'Successfully processed and archived documents'
    }
  }
}

// --- Azure Cache for Redis ---

resource redis 'Microsoft.Cache/redis@2023-08-01' = {
  name: redisName
  location: location
  tags: tags
  properties: {
    sku: {
      name: environment == 'prod' ? 'Premium' : 'Basic'
      family: environment == 'prod' ? 'P' : 'C'
      capacity: environment == 'prod' ? 1 : 0
    }
    enableNonSslPort: false
    minimumTlsVersion: '1.2'
    publicNetworkAccess: environment == 'prod' ? 'Disabled' : 'Enabled'
    redisConfiguration: {
      'maxmemory-policy': 'allkeys-lru'
      'maxmemory-reserved': environment == 'prod' ? '300' : '50'
    }
    redisVersion: '6'
  }
}

// ============================================================================
// SECURITY - Key Vault
// ============================================================================

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enabledForDeployment: false
    enabledForDiskEncryption: false
    enabledForTemplateDeployment: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enableRbacAuthorization: true
    enablePurgeProtection: environment == 'prod' ? true : false
    publicNetworkAccess: environment == 'prod' ? 'Disabled' : 'Enabled'
    networkAcls: {
      defaultAction: environment == 'prod' ? 'Deny' : 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// Store secrets in Key Vault
resource cosmosConnectionStringSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'cosmos-connection-string'
  properties: {
    value: cosmosAccount.listConnectionStrings().connectionStrings[0].connectionString
  }
}

resource cosmosPrimaryKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'cosmos-primary-key'
  properties: {
    value: cosmosAccount.listKeys().primaryMasterKey
  }
}

resource searchApiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'search-api-key'
  properties: {
    value: aiSearch.listAdminKeys().primaryKey
  }
}

resource openaiApiKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'openai-api-key'
  properties: {
    value: openai.listKeys().key1
  }
}

resource docIntelligenceKeySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'doc-intelligence-key'
  properties: {
    value: documentIntelligence.listKeys().key1
  }
}

resource redisUrlSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'redis-url'
  properties: {
    value: 'rediss://:${redis.listKeys().primaryKey}@${redis.properties.hostName}:${redis.properties.sslPort}/0'
  }
}

resource storageConnectionStringSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: keyVault
  name: 'storage-connection-string'
  properties: {
    value: 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageAccount.listKeys().keys[0].value};EndpointSuffix=${az.environment().suffixes.storage}'
  }
}

// --- RBAC Role Assignments ---

resource acrRegistry 'Microsoft.ContainerRegistry/registries@2023-07-01' = if (acrUseManagedIdentity && acrCreate) {
  name: acrEffectiveName
  location: location
  tags: tags
  sku: {
    name: acrSku
  }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
}

resource acrRegistryExisting 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = if (acrUseManagedIdentity && !acrCreate) {
  name: acrEffectiveName
}

// Key Vault Secrets User for Managed Identity
resource kvSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentity.id, '4633458b-17de-408a-b874-0445c86b69e6')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Cognitive Services OpenAI User for Managed Identity
resource openaiUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openai.id, managedIdentity.id, '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
  scope: openai
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd') // Cognitive Services OpenAI User
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Search Index Data Contributor for Managed Identity
resource searchDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(aiSearch.id, managedIdentity.id, '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
  scope: aiSearch
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7') // Search Index Data Contributor
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Storage Blob Data Contributor for Managed Identity
resource storageBlobContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentity.id, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Cosmos DB Built-in Data Contributor for Managed Identity
resource cosmosDataContributorRole 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2023-11-15' = {
  parent: cosmosAccount
  name: guid(cosmosAccount.id, managedIdentity.id, '00000000-0000-0000-0000-000000000002')
  properties: {
    roleDefinitionId: '${cosmosAccount.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002' // Cosmos DB Built-in Data Contributor
    principalId: managedIdentity.properties.principalId
    scope: cosmosAccount.id
  }
}

// AcrPull role for managed identity (required for private ACR image pulls).
resource acrPullRoleOnCreatedAcr 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (acrUseManagedIdentity && acrCreate) {
  name: guid(acrRegistry.id, managedIdentity.id, '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  scope: acrRegistry
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    ) // AcrPull
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource acrPullRoleOnExistingAcr 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (acrUseManagedIdentity && !acrCreate) {
  name: guid(acrRegistryExisting.id, managedIdentity.id, '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  scope: acrRegistryExisting
  properties: {
    roleDefinitionId: subscriptionResourceId(
      'Microsoft.Authorization/roleDefinitions',
      '7f951dda-4ed3-4680-a7ca-43fe172d538d'
    ) // AcrPull
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// PRIVATE ENDPOINTS
// ============================================================================

// --- Cosmos DB Private Endpoint ---

resource cosmosPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = if (environment == 'prod') {
  name: '${cosmosAccountName}-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/${dataSubnetName}'
    }
    privateLinkServiceConnections: [
      {
        name: '${cosmosAccountName}-plsc'
        properties: {
          privateLinkServiceId: cosmosAccount.id
          groupIds: [
            'Sql'
          ]
        }
      }
    ]
  }
}

resource cosmosPrivateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (environment == 'prod') {
  parent: cosmosPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'cosmos-dns-config'
        properties: {
          privateDnsZoneId: cosmosPrivateDnsZone.id
        }
      }
    ]
  }
}

// --- Key Vault Private Endpoint ---

resource keyVaultPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = if (environment == 'prod') {
  name: '${keyVaultName}-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/${dataSubnetName}'
    }
    privateLinkServiceConnections: [
      {
        name: '${keyVaultName}-plsc'
        properties: {
          privateLinkServiceId: keyVault.id
          groupIds: [
            'vault'
          ]
        }
      }
    ]
  }
}

resource keyVaultPrivateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (environment == 'prod') {
  parent: keyVaultPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'keyvault-dns-config'
        properties: {
          privateDnsZoneId: keyVaultPrivateDnsZone.id
        }
      }
    ]
  }
}

// --- AI Search Private Endpoint ---

resource searchPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = if (environment == 'prod') {
  name: '${aiSearchName}-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/${aiSubnetName}'
    }
    privateLinkServiceConnections: [
      {
        name: '${aiSearchName}-plsc'
        properties: {
          privateLinkServiceId: aiSearch.id
          groupIds: [
            'searchService'
          ]
        }
      }
    ]
  }
}

resource searchPrivateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (environment == 'prod') {
  parent: searchPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'search-dns-config'
        properties: {
          privateDnsZoneId: searchPrivateDnsZone.id
        }
      }
    ]
  }
}

// --- Azure OpenAI Private Endpoint ---

resource openaiPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = if (environment == 'prod') {
  name: '${openaiName}-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/${aiSubnetName}'
    }
    privateLinkServiceConnections: [
      {
        name: '${openaiName}-plsc'
        properties: {
          privateLinkServiceId: openai.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource openaiPrivateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (environment == 'prod') {
  parent: openaiPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'openai-dns-config'
        properties: {
          privateDnsZoneId: openaiPrivateDnsZone.id
        }
      }
    ]
  }
}

// --- Document Intelligence Private Endpoint ---

resource docIntelPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-11-01' = if (environment == 'prod') {
  name: '${docIntelligenceName}-pe'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: '${vnet.id}/subnets/${aiSubnetName}'
    }
    privateLinkServiceConnections: [
      {
        name: '${docIntelligenceName}-plsc'
        properties: {
          privateLinkServiceId: documentIntelligence.id
          groupIds: [
            'account'
          ]
        }
      }
    ]
  }
}

resource docIntelPrivateEndpointDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2023-11-01' = if (environment == 'prod') {
  parent: docIntelPrivateEndpoint
  name: 'default'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'docintel-dns-config'
        properties: {
          privateDnsZoneId: cognitivePrivateDnsZone.id
        }
      }
    ]
  }
}

// ============================================================================
// COMPUTE - Container Apps
// ============================================================================

resource containerAppEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppEnvName
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    daprAIInstrumentationKey: appInsights.properties.InstrumentationKey
    vnetConfiguration: {
      infrastructureSubnetId: '${vnet.id}/subnets/${appSubnetName}'
      internal: containerAppEnvironmentInternal
    }
    zoneRedundant: environment == 'prod'
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

var storageBlobEndpoint = 'https://${storageAccount.name}.blob.${az.environment().suffixes.storage}/'

var containerAppBaseSecrets = [
  {
    name: 'cosmos-connection-string'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/cosmos-connection-string'
    identity: managedIdentity.id
  }
  {
    name: 'cosmos-primary-key'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/cosmos-primary-key'
    identity: managedIdentity.id
  }
  {
    name: 'search-api-key'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/search-api-key'
    identity: managedIdentity.id
  }
  {
    name: 'openai-api-key'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/openai-api-key'
    identity: managedIdentity.id
  }
  {
    name: 'doc-intelligence-key'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/doc-intelligence-key'
    identity: managedIdentity.id
  }
  {
    name: 'redis-url'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/redis-url'
    identity: managedIdentity.id
  }
]

var containerAppSecrets = environment == 'prod'
  ? containerAppBaseSecrets
  : concat(containerAppBaseSecrets, [
      {
        name: 'storage-connection-string'
        keyVaultUrl: '${keyVault.properties.vaultUri}secrets/storage-connection-string'
        identity: managedIdentity.id
      }
    ])

var containerAppBaseEnv = [
  {
    name: 'ENVIRONMENT'
    value: environment
  }
  {
    name: 'CDSS_AZURE_OPENAI_ENDPOINT'
    value: openai.properties.endpoint
  }
  {
    name: 'CDSS_AZURE_OPENAI_API_KEY'
    secretRef: 'openai-api-key'
  }
  {
    name: 'CDSS_AZURE_OPENAI_DEPLOYMENT_NAME'
    value: gpt4oDeploymentName
  }
  {
    name: 'CDSS_AZURE_OPENAI_MINI_DEPLOYMENT_NAME'
    value: gpt4oMiniDeploymentName
  }
  {
    name: 'CDSS_AZURE_OPENAI_EMBEDDING_DEPLOYMENT'
    value: embeddingDeploymentName
  }
  {
    name: 'CDSS_AZURE_OPENAI_API_VERSION'
    value: '2024-12-01-preview'
  }
  {
    name: 'CDSS_AZURE_SEARCH_ENDPOINT'
    value: 'https://${aiSearch.name}.search.windows.net'
  }
  {
    name: 'CDSS_AZURE_SEARCH_API_KEY'
    secretRef: 'search-api-key'
  }
  {
    name: 'CDSS_AZURE_SEARCH_PATIENT_RECORDS_INDEX'
    value: 'patient-records'
  }
  {
    name: 'CDSS_AZURE_SEARCH_TREATMENT_PROTOCOLS_INDEX'
    value: 'treatment-protocols'
  }
  {
    name: 'CDSS_AZURE_SEARCH_MEDICAL_LITERATURE_INDEX'
    value: 'medical-literature-cache'
  }
  {
    name: 'CDSS_AZURE_SEARCH_PATIENT_RECORDS_SEMANTIC_CONFIG'
    value: 'patient-records-semantic'
  }
  {
    name: 'CDSS_AZURE_SEARCH_TREATMENT_PROTOCOLS_SEMANTIC_CONFIG'
    value: 'protocols-semantic'
  }
  {
    name: 'CDSS_AZURE_SEARCH_MEDICAL_LITERATURE_SEMANTIC_CONFIG'
    value: 'literature-semantic'
  }
  {
    name: 'CDSS_AZURE_COSMOS_ENDPOINT'
    value: cosmosAccount.properties.documentEndpoint
  }
  {
    name: 'CDSS_AZURE_COSMOS_USE_ENTRA_ID'
    value: environment == 'prod' ? 'true' : 'false'
  }
  {
    name: 'CDSS_AZURE_COSMOS_DATABASE_NAME'
    value: cosmosDatabaseName
  }
  {
    name: 'CDSS_AZURE_COSMOS_PATIENT_PROFILES_CONTAINER'
    value: 'patient-profiles'
  }
  {
    name: 'CDSS_AZURE_COSMOS_CONVERSATION_HISTORY_CONTAINER'
    value: 'conversation-history'
  }
  {
    name: 'CDSS_AZURE_COSMOS_EMBEDDING_CACHE_CONTAINER'
    value: 'embedding-cache'
  }
  {
    name: 'CDSS_AZURE_COSMOS_AUDIT_LOG_CONTAINER'
    value: 'audit-log'
  }
  {
    name: 'CDSS_AZURE_COSMOS_AGENT_STATE_CONTAINER'
    value: 'agent-state'
  }
  {
    name: 'CDSS_AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT'
    value: documentIntelligence.properties.endpoint
  }
  {
    name: 'CDSS_AZURE_DOCUMENT_INTELLIGENCE_KEY'
    secretRef: 'doc-intelligence-key'
  }
  {
    name: 'CDSS_AZURE_BLOB_PROTOCOLS_CONTAINER'
    value: 'treatment-protocols'
  }
  {
    name: 'CDSS_AZURE_BLOB_ENDPOINT'
    value: storageBlobEndpoint
  }
  {
    name: 'CDSS_AZURE_BLOB_USE_ENTRA_ID'
    value: environment == 'prod' ? 'true' : 'false'
  }
  {
    name: 'CDSS_REDIS_URL'
    secretRef: 'redis-url'
  }
  {
    name: 'CDSS_AZURE_KEY_VAULT_URL'
    value: keyVault.properties.vaultUri
  }
  {
    name: 'CDSS_CORS_ORIGINS'
    value: string(corsAllowedOrigins)
  }
  {
    name: 'CDSS_CORS_ALLOW_METHODS'
    value: '["GET","POST","PUT","PATCH","DELETE","OPTIONS"]'
  }
  {
    name: 'CDSS_CORS_ALLOW_HEADERS'
    value: '["Authorization","Content-Type","X-Request-ID"]'
  }
  {
    name: 'CDSS_CORS_EXPOSE_HEADERS'
    value: '["X-Request-ID","X-Trace-ID"]'
  }
  {
    name: 'CDSS_CORS_ALLOW_CREDENTIALS'
    value: 'true'
  }
  {
    name: 'CDSS_AUTH_ENABLED'
    value: string(authEnabled)
  }
  {
    name: 'CDSS_AUTH_TENANT_ID'
    value: subscription().tenantId
  }
  {
    name: 'CDSS_AUTH_AUDIENCE'
    value: authAudience
  }
  {
    name: 'CDSS_AUTH_REQUIRED_SCOPES'
    value: string(authRequiredScopes)
  }
  {
    name: 'CDSS_LOG_LEVEL'
    value: environment == 'prod' ? 'INFO' : 'DEBUG'
  }
  {
    name: 'AZURE_CLIENT_ID'
    value: managedIdentity.properties.clientId
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: appInsights.properties.ConnectionString
  }
]

var containerAppEnvVars = environment == 'prod'
  ? containerAppBaseEnv
  : concat(containerAppBaseEnv, [
      {
        name: 'CDSS_AZURE_COSMOS_KEY'
        secretRef: 'cosmos-primary-key'
      }
      {
        name: 'CDSS_AZURE_BLOB_CONNECTION_STRING'
        secretRef: 'storage-connection-string'
      }
    ])

resource containerApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: containerAppName
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: containerAppEnv.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Multiple'
      registries: acrUseManagedIdentity ? [
        {
          server: acrLoginServer
          identity: managedIdentity.id
        }
      ] : []
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        corsPolicy: {
          allowedOrigins: corsAllowedOrigins
          allowedMethods: [
            'GET'
            'POST'
            'PUT'
            'PATCH'
            'DELETE'
            'OPTIONS'
          ]
          allowedHeaders: [
            'Authorization'
            'Content-Type'
            'X-Request-ID'
          ]
          maxAge: 3600
        }
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      maxInactiveRevisions: 3
      secrets: containerAppSecrets
    }
    template: {
      containers: [
        {
          name: 'cdss-api'
          image: containerImage
          resources: {
            cpu: json(environment == 'prod' ? '2.0' : '0.5')
            memory: environment == 'prod' ? '4Gi' : '1Gi'
          }
          env: containerAppEnvVars
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                path: '/api/v1/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 30
              periodSeconds: 30
              failureThreshold: 3
              timeoutSeconds: 5
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/api/v1/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 10
              periodSeconds: 15
              failureThreshold: 5
              timeoutSeconds: 5
            }
            {
              type: 'Startup'
              httpGet: {
                path: '/api/v1/health'
                port: 8000
                scheme: 'HTTP'
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              failureThreshold: 10
              timeoutSeconds: 5
            }
          ]
        }
      ]
      scale: {
        minReplicas: environment == 'prod' ? 2 : 0
        maxReplicas: environment == 'prod' ? 10 : 3
        rules: [
          {
            name: 'http-scaler'
            http: {
              metadata: {
                concurrentRequests: '50'
              }
            }
          }
        ]
      }
    }
  }
  dependsOn: [
    acrPullRoleOnCreatedAcr
    acrPullRoleOnExistingAcr
    kvSecretsUserRole
    cosmosConnectionStringSecret
    cosmosPrimaryKeySecret
    searchApiKeySecret
    openaiApiKeySecret
    docIntelligenceKeySecret
    redisUrlSecret
    storageConnectionStringSecret
  ]
}

// ============================================================================
// FRONTEND - Azure Static Web Apps
// Note: Static Web Apps requires a repository URL. For manual deployment,
// create via Azure Portal or CLI after infrastructure is provisioned.
// ============================================================================

resource staticWebApp 'Microsoft.Web/staticSites@2023-01-01' = if (environment != 'prod') {
  name: staticWebAppName
  location: location
  tags: tags
  sku: {
    name: 'Free'
    tier: 'Free'
  }
  properties: {
    repositoryUrl: 'https://github.com/placeholder/cdss-frontend'
    branch: 'main'
    buildProperties: {
      appLocation: 'frontend'
      apiLocation: ''
      outputLocation: 'dist'
    }
    provider: 'Custom'
  }
}

resource staticWebAppConfig 'Microsoft.Web/staticSites/config@2023-01-01' = if (environment != 'prod') {
  parent: staticWebApp
  name: 'appsettings'
  properties: {
    VITE_USE_MOCK_API: 'false'
    VITE_API_BASE_URL: 'https://${containerApp.properties.configuration.ingress.fqdn}'
    VITE_AZURE_CLIENT_ID: ''
    VITE_AZURE_TENANT_ID: subscription().tenantId
  }
}

// ============================================================================
// AI SEARCH INDEX DEFINITIONS
// ============================================================================
// Note: Azure AI Search indexes must be created via the REST API or SDK
// after the search service is provisioned. The following deployment script
// resource uses the search management API to create the indexes.
// In practice, you would use a deployment script or post-deployment step.

resource searchIndexDeploymentScript 'Microsoft.Resources/deploymentScripts@2023-08-01' = if (environment != 'prod') {
  name: '${resourcePrefix}-create-search-indexes'
  location: location
  tags: tags
  kind: 'AzureCLI'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    azCliVersion: '2.59.0'
    retentionInterval: 'P1D'
    timeout: 'PT30M'
    cleanupPreference: 'OnSuccess'
    environmentVariables: [
      {
        name: 'SEARCH_ENDPOINT'
        value: 'https://${aiSearch.name}.search.windows.net'
      }
      {
        name: 'SEARCH_ADMIN_KEY'
        secureValue: aiSearch.listAdminKeys().primaryKey
      }
    ]
    scriptContent: '''
      #!/bin/bash
      set -e

      echo "Creating search indexes using az rest..."

      create_index() {
        local index_json="$1"
        local index_name=$(echo "$index_json" | python3 -c "import sys,json;print(json.load(sys.stdin)['name'])")
        echo "Creating/updating index: $index_name"

        az rest --method put \
          --url "${SEARCH_ENDPOINT}/indexes/${index_name}?api-version=2024-05-01-preview" \
          --skip-authorization-header \
          --headers "Content-Type=application/json" "api-key=${SEARCH_ADMIN_KEY}" \
          --body "$index_json" \
          --output none

        echo "Index $index_name created/updated successfully"
      }

      PATIENT_RECORDS_INDEX='{
        "name": "patient-records",
        "fields": [
          {"name": "id", "type": "Edm.String", "key": true, "filterable": true},
          {"name": "document_id", "type": "Edm.String", "filterable": true, "sortable": true},
          {"name": "chunk_index", "type": "Edm.Int32", "filterable": true, "sortable": true},
          {"name": "content", "type": "Edm.String", "searchable": true, "analyzer": "en.microsoft"},
          {"name": "content_vector", "type": "Collection(Edm.Single)", "searchable": true, "dimensions": 3072, "vectorSearchProfile": "vector-profile"},
          {"name": "document_type", "type": "Edm.String", "filterable": true, "facetable": true},
          {"name": "patient_id", "type": "Edm.String", "filterable": true, "sortable": true},
          {"name": "ingested_at", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true},
          {"name": "entity_names", "type": "Collection(Edm.String)", "filterable": true, "searchable": true},
          {"name": "entity_codes", "type": "Collection(Edm.String)", "filterable": true},
          {"name": "metadata", "type": "Edm.String", "searchable": false}
        ],
        "vectorSearch": {
          "algorithms": [
            {"name": "hnsw-algorithm", "kind": "hnsw", "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}}
          ],
          "profiles": [
            {"name": "vector-profile", "algorithm": "hnsw-algorithm"}
          ]
        },
        "semantic": {
          "configurations": [
            {
              "name": "patient-records-semantic",
              "prioritizedFields": {
                "titleField": {"fieldName": "document_type"},
                "prioritizedContentFields": [{"fieldName": "content"}],
                "prioritizedKeywordsFields": [{"fieldName": "entity_names"}]
              }
            }
          ]
        }
      }'

      TREATMENT_PROTOCOLS_INDEX='{
        "name": "treatment-protocols",
        "fields": [
          {"name": "id", "type": "Edm.String", "key": true, "filterable": true},
          {"name": "document_id", "type": "Edm.String", "filterable": true, "sortable": true},
          {"name": "chunk_index", "type": "Edm.Int32", "filterable": true, "sortable": true},
          {"name": "content", "type": "Edm.String", "searchable": true, "analyzer": "en.microsoft"},
          {"name": "content_vector", "type": "Collection(Edm.Single)", "searchable": true, "dimensions": 3072, "vectorSearchProfile": "vector-profile"},
          {"name": "specialty", "type": "Edm.String", "filterable": true, "facetable": true, "searchable": true},
          {"name": "guideline_name", "type": "Edm.String", "filterable": true, "searchable": true, "sortable": true},
          {"name": "version", "type": "Edm.String", "filterable": true, "sortable": true},
          {"name": "is_protocol", "type": "Edm.Boolean", "filterable": true},
          {"name": "document_type", "type": "Edm.String", "filterable": true, "facetable": true},
          {"name": "ingested_at", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true},
          {"name": "entity_names", "type": "Collection(Edm.String)", "filterable": true, "searchable": true},
          {"name": "entity_codes", "type": "Collection(Edm.String)", "filterable": true},
          {"name": "metadata", "type": "Edm.String", "searchable": false}
        ],
        "vectorSearch": {
          "algorithms": [
            {"name": "hnsw-algorithm", "kind": "hnsw", "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}}
          ],
          "profiles": [
            {"name": "vector-profile", "algorithm": "hnsw-algorithm"}
          ]
        },
        "semantic": {
          "configurations": [
            {
              "name": "protocols-semantic",
              "prioritizedFields": {
                "titleField": {"fieldName": "guideline_name"},
                "prioritizedContentFields": [{"fieldName": "content"}],
                "prioritizedKeywordsFields": [{"fieldName": "specialty"}]
              }
            }
          ]
        }
      }'

      MEDICAL_LITERATURE_INDEX='{
        "name": "medical-literature-cache",
        "fields": [
          {"name": "id", "type": "Edm.String", "key": true, "filterable": true},
          {"name": "document_id", "type": "Edm.String", "filterable": true, "sortable": true},
          {"name": "chunk_index", "type": "Edm.Int32", "filterable": true, "sortable": true},
          {"name": "content", "type": "Edm.String", "searchable": true, "analyzer": "en.microsoft"},
          {"name": "content_vector", "type": "Collection(Edm.Single)", "searchable": true, "dimensions": 3072, "vectorSearchProfile": "vector-profile"},
          {"name": "pmid", "type": "Edm.String", "filterable": true, "sortable": true},
          {"name": "title", "type": "Edm.String", "searchable": true, "sortable": true},
          {"name": "journal", "type": "Edm.String", "filterable": true, "facetable": true, "searchable": true},
          {"name": "publication_date", "type": "Edm.String", "filterable": true, "sortable": true},
          {"name": "mesh_terms", "type": "Collection(Edm.String)", "filterable": true, "facetable": true, "searchable": true},
          {"name": "document_type", "type": "Edm.String", "filterable": true, "facetable": true},
          {"name": "ingested_at", "type": "Edm.DateTimeOffset", "filterable": true, "sortable": true},
          {"name": "entity_names", "type": "Collection(Edm.String)", "filterable": true, "searchable": true},
          {"name": "entity_codes", "type": "Collection(Edm.String)", "filterable": true},
          {"name": "metadata", "type": "Edm.String", "searchable": false}
        ],
        "vectorSearch": {
          "algorithms": [
            {"name": "hnsw-algorithm", "kind": "hnsw", "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}}
          ],
          "profiles": [
            {"name": "vector-profile", "algorithm": "hnsw-algorithm"}
          ]
        },
        "semantic": {
          "configurations": [
            {
              "name": "literature-semantic",
              "prioritizedFields": {
                "titleField": {"fieldName": "title"},
                "prioritizedContentFields": [{"fieldName": "content"}],
                "prioritizedKeywordsFields": [{"fieldName": "mesh_terms"}]
              }
            }
          ]
        }
      }'

      create_index "$PATIENT_RECORDS_INDEX"
      create_index "$TREATMENT_PROTOCOLS_INDEX"
      create_index "$MEDICAL_LITERATURE_INDEX"

      echo "All search indexes created successfully"
    '''
  }
  dependsOn: [
    aiSearch
    searchDataContributorRole
    managedIdentity
  ]
}

// ============================================================================
// DIAGNOSTIC SETTINGS
// ============================================================================

resource cosmosDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: '${cosmosAccountName}-diagnostics'
  scope: cosmosAccount
  properties: {
    workspaceId: logAnalytics.id
    logs: [
      {
        category: 'DataPlaneRequests'
        enabled: true
      }
      {
        category: 'QueryRuntimeStatistics'
        enabled: true
      }
      {
        category: 'PartitionKeyStatistics'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'Requests'
        enabled: true
      }
    ]
  }
}

resource searchDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: '${aiSearchName}-diagnostics'
  scope: aiSearch
  properties: {
    workspaceId: logAnalytics.id
    logs: [
      {
        category: 'OperationLogs'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

resource openaiDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: '${openaiName}-diagnostics'
  scope: openai
  properties: {
    workspaceId: logAnalytics.id
    logs: [
      {
        category: 'Audit'
        enabled: true
      }
      {
        category: 'RequestResponse'
        enabled: true
      }
    ]
    metrics: [
      {
        category: 'AllMetrics'
        enabled: true
      }
    ]
  }
}

// ============================================================================
// OUTPUTS
// ============================================================================

@description('Cosmos DB account endpoint')
output cosmosEndpoint string = cosmosAccount.properties.documentEndpoint

@description('AI Search service endpoint')
output searchEndpoint string = 'https://${aiSearch.name}.search.windows.net'

@description('Azure OpenAI endpoint')
output openaiEndpoint string = openai.properties.endpoint

@description('Key Vault URI')
output keyVaultUri string = keyVault.properties.vaultUri

@description('Container App URL')
output containerAppUrl string = 'https://${containerApp.properties.configuration.ingress.fqdn}'

@description('Backend API FQDN')
output backendUrl string = containerApp.properties.configuration.ingress.fqdn

@description('Backend API exposure mode')
output backendApiExposureMode string = apiExposureMode

@description('Container Apps environment internal networking mode')
output containerAppEnvironmentIsInternal bool = containerAppEnvironmentInternal

@description('Static Web App URL (Frontend)')
output staticWebAppUrl string = environment != 'prod' ? 'https://${staticWebAppName}.azurestaticapps.net' : ''

@description('Static Web App name')
output staticWebAppName string = environment != 'prod' ? staticWebApp.name : ''

@description('Application Insights instrumentation key')
output appInsightsKey string = appInsights.properties.InstrumentationKey

@description('Application Insights connection string')
output appInsightsConnectionString string = appInsights.properties.ConnectionString

@description('Managed Identity client ID')
output managedIdentityClientId string = managedIdentity.properties.clientId

@description('Storage account name')
output storageAccountName string = storageAccount.name

@description('Document Intelligence endpoint')
output docIntelligenceEndpoint string = documentIntelligence.properties.endpoint

@description('Redis hostname')
output redisHostname string = redis.properties.hostName

@description('ACR name used for container image pulls when managed identity is enabled')
output acrName string = acrUseManagedIdentity ? acrEffectiveName : ''

@description('ACR login server used for container image pulls when managed identity is enabled')
output acrLoginServer string = acrUseManagedIdentity ? acrLoginServer : ''

@description('VNet ID')
output vnetId string = vnet.id

@description('Resource group name')
output resourceGroupName string = resourceGroup().name

@description('Environment name')
output environment string = environment
