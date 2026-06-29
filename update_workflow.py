import re
import os

filepath = r"c:\Users\DELL\Downloads\AP_ExceptionHandling (2) (1)\AP_ExceptionHandling (3) (1)\AP_ExceptionHandling (1)\AP_ExceptionHandling\Workflow.xaml"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

ns_to_add = """      <x:String>Newtonsoft.Json.Linq</x:String>
      <x:String>Newtonsoft.Json</x:String>
      <x:String>UiPath.Web</x:String>
      <x:String>System.Security</x:String>
      <x:String>UiPath.Web.Activities</x:String>"""

if "Newtonsoft.Json.Linq" not in content:
    content = content.replace("</sco:Collection>\n  </TextExpression.NamespacesForImplementation>", ns_to_add + "\n    </sco:Collection>\n  </TextExpression.NamespacesForImplementation>")

asm_to_add = """      <AssemblyReference>Newtonsoft.Json</AssemblyReference>
      <AssemblyReference>UiPath.Web</AssemblyReference>
      <AssemblyReference>UiPath.Web.Activities</AssemblyReference>"""

if "UiPath.Web.Activities" not in content:
    content = content.replace("</sco:Collection>\n  </TextExpression.ReferencesForImplementation>", asm_to_add + "\n    </sco:Collection>\n  </TextExpression.ReferencesForImplementation>")

try_sequence_replacement = """          <Sequence DisplayName="Try" sap:VirtualizedContainerService.HintSize="450,1500" sap2010:WorkflowViewState.IdRef="Sequence_3">
            <Sequence.Variables>
              <Variable x:TypeArguments="ui:QueueItem" Name="TransactionItem" />
              <Variable x:TypeArguments="x:String" Name="ProcessItemResponseStr" />
              <Variable x:TypeArguments="njl:JObject" Name="ProcessItemResponseJson" />
              <Variable x:TypeArguments="x:Int32" Name="StatusCode" />
            </Sequence.Variables>
            <sap:WorkflowViewStateService.ViewState>
              <scg:Dictionary x:TypeArguments="x:String, x:Object">
                <x:Boolean x:Key="IsExpanded">True</x:Boolean>
              </scg:Dictionary>
            </sap:WorkflowViewStateService.ViewState>
            
            <ui:StartProcess Arguments="app.py --api" DisplayName="Start Process" FileName="python.exe" sap:VirtualizedContainerService.HintSize="416,124" sap2010:WorkflowViewState.IdRef="StartProcess_1" StartType="Asynchronously" Timeout="60000" WorkingDirectory="C:\\Users\\DELL\\Downloads\\AP_ExceptionHandling (1)\\AP_ExceptionHandling" />
            
            <Delay Duration="00:00:05" DisplayName="Delay 5s for API" sap2010:WorkflowViewState.IdRef="Delay_1" />
            
            <ui:GetQueueItem ContinueOnError="{x:Null}" TimeoutMS="{x:Null}" DisplayName="Get Transaction Item" FolderPath="Shared" sap:VirtualizedContainerService.HintSize="416,182" sap2010:WorkflowViewState.IdRef="GetQueueItem_1" QueueType="ExceptionQueue" TransactionItem="[TransactionItem]" />
            
            <If Condition="[TransactionItem IsNot Nothing]" DisplayName="If Transaction Item Exists" sap2010:WorkflowViewState.IdRef="If_1">
              <If.Then>
                <Sequence DisplayName="Process Item" sap2010:WorkflowViewState.IdRef="Sequence_2">
                  <Sequence.Variables>
                    <Variable x:TypeArguments="x:String" Name="QueueItemJsonString" />
                  </Sequence.Variables>
                  <sap:WorkflowViewStateService.ViewState>
                    <scg:Dictionary x:TypeArguments="x:String, x:Object">
                      <x:Boolean x:Key="IsExpanded">True</x:Boolean>
                    </scg:Dictionary>
                  </sap:WorkflowViewStateService.ViewState>
                  
                  <Assign DisplayName="Serialize Queue Item" sap2010:WorkflowViewState.IdRef="Assign_1">
                    <Assign.To>
                      <OutArgument x:TypeArguments="x:String">[QueueItemJsonString]</OutArgument>
                    </Assign.To>
                    <Assign.Value>
                      <InArgument x:TypeArguments="x:String">[Newtonsoft.Json.JsonConvert.SerializeObject(TransactionItem.SpecificContent)]</InArgument>
                    </Assign.Value>
                  </Assign>

                  <ui:HttpClient Body="[QueueItemJsonString]" BodyFormat="application/json" ClientCertificate="{x:Null}" ClientCertificatePassword="{x:Null}" ConsumerKey="{x:Null}" ConsumerSecret="{x:Null}" ContinueOnError="{x:Null}" FileAttachments="{x:Null}" OAuth1Token="{x:Null}" OAuth1TokenSecret="{x:Null}" OAuth2Token="{x:Null}" Password="{x:Null}" ResourcePath="{x:Null}" ResponseAttachment="{x:Null}" ResponseHeaders="{x:Null}" SecureClientCertificatePassword="{x:Null}" SecurePassword="{x:Null}" Username="{x:Null}" AcceptFormat="JSON" AuthenticationType="None" DisplayName="HTTP Request - Process Item" EnableSSLVerification="True" EndPoint="http://127.0.0.1:8000/process-item" sap2010:WorkflowViewState.IdRef="HttpClient_1" Method="POST" Result="[ProcessItemResponseStr]" StatusCode="[StatusCode]" TimeoutMS="30000">
                    <ui:HttpClient.Attachments>
                      <scg:Dictionary x:TypeArguments="x:String, InArgument(x:String)" />
                    </ui:HttpClient.Attachments>
                    <ui:HttpClient.Cookies>
                      <scg:Dictionary x:TypeArguments="x:String, InArgument(x:String)" />
                    </ui:HttpClient.Cookies>
                    <ui:HttpClient.Headers>
                      <InArgument x:TypeArguments="x:String" x:Key="Content-Type">application/json</InArgument>
                    </ui:HttpClient.Headers>
                    <ui:HttpClient.Parameters>
                      <scg:Dictionary x:TypeArguments="x:String, InArgument(x:String)" />
                    </ui:HttpClient.Parameters>
                    <ui:HttpClient.UrlSegments>
                      <scg:Dictionary x:TypeArguments="x:String, InArgument(x:String)" />
                    </ui:HttpClient.UrlSegments>
                  </ui:HttpClient>

                  <ui:DeserializeJson x:TypeArguments="njl:JObject" JsonSample="{x:Null}" Settings="{x:Null}" DisplayName="Deserialize JSON" sap2010:WorkflowViewState.IdRef="DeserializeJson`1_1" JsonObject="[ProcessItemResponseJson]" JsonString="[ProcessItemResponseStr]" />
                  
                  <If Condition="[ProcessItemResponseJson(&quot;communication&quot;) IsNot Nothing AndAlso ProcessItemResponseJson(&quot;communication&quot;).Type &lt;&gt; Newtonsoft.Json.Linq.JTokenType.Null]" DisplayName="If Communication Exists" sap2010:WorkflowViewState.IdRef="If_2">
                    <If.Then>
                      <Sequence DisplayName="Send Email" sap2010:WorkflowViewState.IdRef="Sequence_6">
                        <Sequence.Variables>
                          <Variable x:TypeArguments="x:String" Name="EmailPayloadStr" />
                          <Variable x:TypeArguments="x:String" Name="EmailResponseStr" />
                        </Sequence.Variables>
                        <sap:WorkflowViewStateService.ViewState>
                          <scg:Dictionary x:TypeArguments="x:String, x:Object">
                            <x:Boolean x:Key="IsExpanded">True</x:Boolean>
                          </scg:Dictionary>
                        </sap:WorkflowViewStateService.ViewState>
                        
                        <Assign DisplayName="Serialize Email Payload" sap2010:WorkflowViewState.IdRef="Assign_2">
                          <Assign.To>
                            <OutArgument x:TypeArguments="x:String">[EmailPayloadStr]</OutArgument>
                          </Assign.To>
                          <Assign.Value>
                            <InArgument x:TypeArguments="x:String">[ProcessItemResponseJson("communication").ToString(Newtonsoft.Json.Formatting.None)]</InArgument>
                          </Assign.Value>
                        </Assign>

                        <ui:HttpClient Body="[EmailPayloadStr]" BodyFormat="application/json" ClientCertificate="{x:Null}" ClientCertificatePassword="{x:Null}" ConsumerKey="{x:Null}" ConsumerSecret="{x:Null}" ContinueOnError="{x:Null}" FileAttachments="{x:Null}" OAuth1Token="{x:Null}" OAuth1TokenSecret="{x:Null}" OAuth2Token="{x:Null}" Password="{x:Null}" ResourcePath="{x:Null}" ResponseAttachment="{x:Null}" ResponseHeaders="{x:Null}" SecureClientCertificatePassword="{x:Null}" SecurePassword="{x:Null}" Username="{x:Null}" AcceptFormat="JSON" AuthenticationType="None" DisplayName="HTTP Request - Send Email" EnableSSLVerification="True" EndPoint="http://127.0.0.1:8000/send-email" sap2010:WorkflowViewState.IdRef="HttpClient_2" Method="POST" Result="[EmailResponseStr]" StatusCode="[StatusCode]" TimeoutMS="30000">
                          <ui:HttpClient.Attachments>
                            <scg:Dictionary x:TypeArguments="x:String, InArgument(x:String)" />
                          </ui:HttpClient.Attachments>
                          <ui:HttpClient.Cookies>
                            <scg:Dictionary x:TypeArguments="x:String, InArgument(x:String)" />
                          </ui:HttpClient.Cookies>
                          <ui:HttpClient.Headers>
                            <InArgument x:TypeArguments="x:String" x:Key="Content-Type">application/json</InArgument>
                          </ui:HttpClient.Headers>
                          <ui:HttpClient.Parameters>
                            <scg:Dictionary x:TypeArguments="x:String, InArgument(x:String)" />
                          </ui:HttpClient.Parameters>
                          <ui:HttpClient.UrlSegments>
                            <scg:Dictionary x:TypeArguments="x:String, InArgument(x:String)" />
                          </ui:HttpClient.UrlSegments>
                        </ui:HttpClient>
                      </Sequence>
                    </If.Then>
                  </If>
                  
                  <ui:SetTransactionStatus ContinueOnError="{x:Null}" ServiceBaseAddress="{x:Null}" TimeoutMS="{x:Null}" DisplayName="Set Transaction Status" ErrorType="Business" FolderPath="Shared" Reason="Processed by Agent" sap2010:WorkflowViewState.IdRef="SetTransactionStatus_1" Status="Successful" TransactionItem="[TransactionItem]">
                    <ui:SetTransactionStatus.Analytics>
                      <scg:Dictionary x:TypeArguments="x:String, InArgument" />
                    </ui:SetTransactionStatus.Analytics>
                    <ui:SetTransactionStatus.Output>
                      <scg:Dictionary x:TypeArguments="x:String, InArgument" />
                    </ui:SetTransactionStatus.Output>
                  </ui:SetTransactionStatus>

                </Sequence>
              </If.Then>
            </If>
          </Sequence>"""

content = re.sub(r'<Sequence DisplayName="Try" .*?</Sequence>', lambda m: try_sequence_replacement, content, flags=re.DOTALL)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)
