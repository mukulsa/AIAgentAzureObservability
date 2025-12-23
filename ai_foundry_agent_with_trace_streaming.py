# simple_chat.py
import asyncio
import json
import logging
import os

from azure.ai.agents.aio import AgentsClient
from azure.ai.agents.models import (
    ThreadMessage,
    MessageDeltaChunk,
    ThreadRun,
    AsyncAgentEventHandler,
    ListSortOrder,
    RunStep,
    RunStepType,
    RunStepStatus
)
from azure.identity.aio import DefaultAzureCredential

from opentelemetry import trace
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from azure.monitor.opentelemetry import configure_azure_monitor
from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor

from dotenv import load_dotenv

# -------------------------------
# Load .env
# -------------------------------
load_dotenv()
APPLICATION_INSIGHTS_CONNECTION_STRING = os.getenv("APPLICATION_INSIGHTS_CONNECTION_STRING")
AZURE_AI_PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT")
AGENT_ID1=os.getenv("AGENT_ID1")

# -------------------------------
# OpenTelemetry & App Insights
# -------------------------------

os.environ["AZURE_TRACING_GEN_AI_CONTENT_RECORDING_ENABLED"] = "true" 

# Setup logging
logging.basicConfig(level=logging.ERROR)
# logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent_chat")


configure_azure_monitor(
    connection_string=APPLICATION_INSIGHTS_CONNECTION_STRING,
    enable_live_metrics=True,
    logger_name="agent_chat"
)
OpenAIInstrumentor().instrument()

# Setup tracer
tracer = trace.get_tracer(__name__)

# --- Event Handler (like in /chat) ---
class MyEventHandler(AsyncAgentEventHandler[str]):
    async def on_message_delta(self, delta: MessageDeltaChunk):
        logger.info(f"Delta: {delta.text}")
        return json.dumps({"type": "message", "content": delta.text})

    async def on_thread_message(self, message: ThreadMessage):
        if message.status == "completed":
            logger.info(f"Final Message: {message.text_messages[0].text.value}")
            return json.dumps({"type": "completed_message", "content": message.text_messages[0].text.value})

    async def on_thread_run(self, run: ThreadRun):
        logger.info(f"Run status: {run.status}")
        return json.dumps({"type": "thread_run", "status": run.status})

    async def on_run_step(self, step: RunStep):
        if step.type == RunStepType.TOOL_CALLS and step.status == RunStepStatus.COMPLETED:
            logger.info(f"Tool details: {step.step_details}")
        #     return json.dumps({
        #     "type": "tool_call",
        #     "status": step.status,
        #     "details": step.step_details
        # })

    async def on_error(self, error: Exception):
        logger.error(f"Error in agent run: {error}")
        return json.dumps({"type": "error", "error": str(error)})

    async def on_done(self):
        logger.info("Stream finished")
        return json.dumps({"type": "stream_end"})
    


# --- Main logic (like /chat POST handler) ---
async def main():
    # Setup client
    endpoint = AZURE_AI_PROJECT_ENDPOINT

    async with DefaultAzureCredential() as credential,  \
            AgentsClient(credential=credential, endpoint=endpoint) as agent_client:

        agent = await agent_client.get_agent(AGENT_ID1)
    
        # Inject trace context
        carrier = {}
        TraceContextTextMapPropagator().inject(carrier)
        ctx = TraceContextTextMapPropagator().extract(carrier=carrier)

        with tracer.start_as_current_span("azure_ai_foundry_chat_with_streaming", context=ctx) as span:
            # Create or get thread
            thread = await agent_client.threads.create()
            thread_id = thread.id
            agent_id = agent.id

            span.set_attribute("agent_id", agent_id)
            span.set_attribute("thread_id", thread_id)

            logger.info(f"Using agent {agent_id}, thread {thread_id}")

            # Send user message
            user_input = input("You: ")
            await agent_client.messages.create(
                thread_id=thread_id,
                role="user",
                content=user_input,
            )

            # Stream results
            async with await agent_client.runs.stream(
                thread_id=thread_id,
                agent_id=agent_id,
                event_handler=MyEventHandler(),
            ) as stream:
                async for event in stream:
                    _, _, result = event
                    if result:
                        logger.info(f"EVENT: {result}")

            # After run, collect messages
            messages = agent_client.messages.list(thread_id=thread_id, order=ListSortOrder.ASCENDING)
            async for msg in messages:
                if msg.text_messages:
                    with tracer.start_as_current_span("message_post_processing"):
                        output_text = msg.text_messages[-1].text.value
                        print(f"{msg.role}: {output_text}")


if __name__ == "__main__":
    asyncio.run(main())
