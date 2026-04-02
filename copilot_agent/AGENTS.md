# Copilot Agent Instructions

## Scope

Estas instrucciones aplican a `copilot_agent/`.

## Mission

Mantener este servicio como runtime dedicado del copiloto clínico:

- separado del backend principal
- orientado a LangGraph Graph API
- con estado durable fuera de memoria local
- sin convertirse en una segunda fuente de verdad clínica

## Boundaries

- no exponer endpoints públicos al navegador
- no aplicar cambios clínicos sensibles sin review externo
- no tocar directamente la DB clínica operativa para writes finales
- no mover auth de usuarios o lógica de permisos desde Django a este servicio

## Code Rules

- preferir funciones pequeñas y nodos explícitos
- el estado del grafo debe ser fácil de inspeccionar y extender
- los tools deben ser estrechos y auditables
- comentarios solo para intent, guard rails o tradeoffs

## Docs

- mantener README y docs de arquitectura al día cuando cambien contratos, runtime, memoria o despliegue
