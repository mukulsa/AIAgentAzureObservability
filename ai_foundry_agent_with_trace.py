import os #New
from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from azure.ai.agents.models import ListSortOrder
from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator #New
from azure.monitor.opentelemetry import configure_azure_monitor  #New
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor  #New


project = AIProjectClient(
    credential=DefaultAzureCredential(),
    endpoint="https://sabharwal-mukul-agent-foundry-re.services.ai.azure.com/api/projects/sabharwal_mukul-agent")

agent = project.agents.get_agent("asst_u1G5jkLyhB9kS0wBLtnt5o0a")

thread = project.agents.threads.create()
print(f"Created thread, ID: {thread.id}")

# -------------------------------
# OpenTelemetry & App Insights
# -------------------------------

os.environ["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = "true" 

# Your app insights connection string #New
CONNECTION_STRING="InstrumentationKey=4485d4db-5424-4e7f-8421-ac15634076a1;IngestionEndpoint=https://eastus2-3.in.applicationinsights.azure.com/;LiveEndpoint=https://eastus2.livediagnostics.monitor.azure.com/;ApplicationId=3e795b8a-2d22-4716-bd23-453c0b60a04c"
# Get the tracer instance
tracer = trace.get_tracer(__name__) #New

configure_azure_monitor(connection_string=CONNECTION_STRING) #New
OpenAIInstrumentor().instrument()

with tracer.start_as_current_span("ai_foundry_agent") as span:

    thread = project.agents.threads.create()
    print(f"Created thread, ID: {thread.id}")

    span.set_attribute("agent_id", agent.id)
    span.set_attribute("thread_id", thread.id)

    message = project.agents.messages.create(
        thread_id=thread.id,
        role="user",
        content="What number does Chris Simpson wear?"
    )

    run = project.agents.runs.create_and_process(
        thread_id=thread.id,
        agent_id=agent.id
    )

    span.set_attribute("run_status", run.status)

    if run.status == "failed":
        span.set_attribute("run_error", run.last_error)
        print(f"Run failed: {run.last_error}")

    else:
        messages = project.agents.messages.list(
            thread_id=thread.id,
            order=ListSortOrder.ASCENDING
        )

        for message in messages:
            if message.text_messages:
                output_text = message.text_messages[-1].text.value
                print(f"{message.role}: {output_text}")

# message = project.agents.messages.create(
#     thread_id=thread.id,
#     role="user",
#     content="What number does Chris wear?"
# )

# run = project.agents.runs.create_and_process(
#     thread_id=thread.id,
#     agent_id=agent.id)

# if run.status == "failed":
#     print(f"Run failed: {run.last_error}")
# else:
#     messages = project.agents.messages.list(thread_id=thread.id, order=ListSortOrder.ASCENDING)

#     for message in messages:
#         if message.text_messages:
#             print(f"{message.role}: {message.text_messages[-1].text.value}")