import { FetchInstrumentation } from "@opentelemetry/instrumentation-fetch";
import { registerInstrumentations } from "@opentelemetry/instrumentation";
import { XMLHttpRequestInstrumentation } from "@opentelemetry/instrumentation-xml-http-request";
import { OTLPTraceExporter } from "@opentelemetry/exporter-trace-otlp-http";
import { Resource } from "@opentelemetry/resources";
import { WebTracerProvider } from "@opentelemetry/sdk-trace-web";
import { BatchSpanProcessor } from "@opentelemetry/sdk-trace-base";

const tracesUrl = import.meta.env.VITE_OTEL_EXPORTER_OTLP_TRACES_URL as
  | string
  | undefined;
const serviceName =
  (import.meta.env.VITE_OTEL_SERVICE_NAME as string | undefined) ||
  "vexthealth-webapp";

if (typeof window !== "undefined" && import.meta.env.DEV && tracesUrl?.trim()) {
  const provider = new WebTracerProvider({
    resource: new Resource({
      "service.name": serviceName,
    }),
  });
  provider.addSpanProcessor(
    new BatchSpanProcessor(
      new OTLPTraceExporter({
        url: tracesUrl.trim(),
      })
    )
  );
  provider.register();

  const apiBase = (import.meta.env.VITE_API_URL as string | undefined)?.trim();
  const propagateTraceHeaderCorsUrls = apiBase?.length
    ? [new RegExp(apiBase.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))]
    : [/.*/];

  registerInstrumentations({
    instrumentations: [
      new FetchInstrumentation({
        propagateTraceHeaderCorsUrls,
        clearTimingResources: true,
      }),
      new XMLHttpRequestInstrumentation({
        propagateTraceHeaderCorsUrls,
        clearTimingResources: true,
      }),
    ],
  });
}
