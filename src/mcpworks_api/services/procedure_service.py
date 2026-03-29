"""Procedure service — CRUD, versioning, execution management."""

import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mcpworks_api.core.exceptions import ConflictError, NotFoundError
from mcpworks_api.models.namespace_service import NamespaceService
from mcpworks_api.models.procedure import (
    Procedure,
    ProcedureExecution,
    ProcedureVersion,
)
from mcpworks_api.services.function import FunctionService

logger = structlog.get_logger(__name__)


class ProcedureService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_procedure(
        self,
        namespace_id: uuid.UUID,
        service_name: str,
        name: str,
        steps: list[dict],
        description: str | None = None,
        created_by: str | None = None,
    ) -> Procedure:
        svc_result = await self.db.execute(
            select(NamespaceService).where(
                NamespaceService.namespace_id == namespace_id,
                NamespaceService.name == service_name,
            )
        )
        service = svc_result.scalar_one_or_none()
        if not service:
            raise NotFoundError(f"Service '{service_name}' not found")

        existing = await self.db.execute(
            select(Procedure).where(
                Procedure.service_id == service.id,
                Procedure.name == name,
                Procedure.is_deleted.is_(False),
            )
        )
        if existing.scalar_one_or_none():
            raise ConflictError(f"Procedure '{name}' already exists in service '{service_name}'")

        fn_service = FunctionService(self.db)
        for i, step in enumerate(steps):
            ref = step["function_ref"]
            if "." not in ref:
                raise ValueError(f"Step {i + 1}: function_ref must be in 'service.function' format")
            svc_name, fn_name = ref.split(".", 1)
            try:
                svc_obj = await fn_service.get_service_by_name(namespace_id, svc_name)
                await fn_service.get_by_name(svc_obj.id, fn_name)
            except Exception:
                raise NotFoundError(f"Step {i + 1}: function '{ref}' not found in namespace")

        normalized_steps = []
        for i, step in enumerate(steps):
            normalized_steps.append(
                {
                    "step_number": i + 1,
                    "name": step["name"],
                    "function_ref": step["function_ref"],
                    "instructions": step["instructions"],
                    "failure_policy": step.get("failure_policy", "required"),
                    "max_retries": step.get("max_retries", 1),
                    "validation": step.get("validation"),
                }
            )

        procedure = Procedure(
            namespace_id=namespace_id,
            service_id=service.id,
            name=name,
            description=description,
            active_version=1,
        )
        self.db.add(procedure)
        await self.db.flush()
        await self.db.refresh(procedure)

        version = ProcedureVersion(
            procedure_id=procedure.id,
            version=1,
            steps=normalized_steps,
            created_by=created_by,
        )
        self.db.add(version)
        await self.db.flush()

        logger.info(
            "procedure_created",
            procedure_id=str(procedure.id),
            name=name,
            service=service_name,
            step_count=len(normalized_steps),
        )
        return procedure

    async def get_procedure(
        self,
        namespace_id: uuid.UUID,
        service_name: str,
        name: str,
    ) -> Procedure:
        svc_result = await self.db.execute(
            select(NamespaceService).where(
                NamespaceService.namespace_id == namespace_id,
                NamespaceService.name == service_name,
            )
        )
        service = svc_result.scalar_one_or_none()
        if not service:
            raise NotFoundError(f"Service '{service_name}' not found")

        result = await self.db.execute(
            select(Procedure)
            .where(
                Procedure.service_id == service.id,
                Procedure.name == name,
                Procedure.is_deleted.is_(False),
            )
            .options(selectinload(Procedure.versions))
        )
        procedure = result.scalar_one_or_none()
        if not procedure:
            raise NotFoundError(f"Procedure '{name}' not found in service '{service_name}'")
        return procedure

    async def list_procedures(
        self,
        namespace_id: uuid.UUID,
        service_name: str,
    ) -> list[Procedure]:
        svc_result = await self.db.execute(
            select(NamespaceService).where(
                NamespaceService.namespace_id == namespace_id,
                NamespaceService.name == service_name,
            )
        )
        service = svc_result.scalar_one_or_none()
        if not service:
            raise NotFoundError(f"Service '{service_name}' not found")

        result = await self.db.execute(
            select(Procedure)
            .where(
                Procedure.service_id == service.id,
                Procedure.is_deleted.is_(False),
            )
            .options(selectinload(Procedure.versions))
            .order_by(Procedure.created_at.desc())
        )
        return list(result.scalars())

    async def update_procedure(
        self,
        namespace_id: uuid.UUID,
        service_name: str,
        name: str,
        steps: list[dict] | None = None,
        description: str | None = None,
        created_by: str | None = None,
    ) -> Procedure:
        procedure = await self.get_procedure(namespace_id, service_name, name)

        if description is not None:
            procedure.description = description

        if steps is not None:
            normalized_steps = []
            for i, step in enumerate(steps):
                normalized_steps.append(
                    {
                        "step_number": i + 1,
                        "name": step["name"],
                        "function_ref": step["function_ref"],
                        "instructions": step["instructions"],
                        "failure_policy": step.get("failure_policy", "required"),
                        "max_retries": step.get("max_retries", 1),
                        "validation": step.get("validation"),
                    }
                )

            new_version_num = procedure.active_version + 1
            version = ProcedureVersion(
                procedure_id=procedure.id,
                version=new_version_num,
                steps=normalized_steps,
                created_by=created_by,
            )
            self.db.add(version)
            procedure.active_version = new_version_num

        await self.db.flush()
        await self.db.refresh(procedure, ["versions"])
        logger.info("procedure_updated", name=name, version=procedure.active_version)
        return procedure

    async def delete_procedure(
        self,
        namespace_id: uuid.UUID,
        service_name: str,
        name: str,
    ) -> None:
        procedure = await self.get_procedure(namespace_id, service_name, name)
        procedure.is_deleted = True
        await self.db.flush()
        logger.info("procedure_deleted", name=name, procedure_id=str(procedure.id))

    async def create_execution(
        self,
        procedure: Procedure,
        trigger_type: str,
        agent_id: uuid.UUID | None = None,
        input_context: dict | None = None,
    ) -> ProcedureExecution:
        execution = ProcedureExecution(
            procedure_id=procedure.id,
            procedure_version=procedure.active_version,
            agent_id=agent_id,
            trigger_type=trigger_type,
            status="running",
            current_step=1,
            step_results=[],
            input_context=input_context,
        )
        self.db.add(execution)
        await self.db.flush()
        await self.db.refresh(execution)
        return execution

    async def get_execution(self, execution_id: uuid.UUID) -> ProcedureExecution:
        result = await self.db.execute(
            select(ProcedureExecution).where(ProcedureExecution.id == execution_id)
        )
        execution = result.scalar_one_or_none()
        if not execution:
            raise NotFoundError(f"Procedure execution '{execution_id}' not found")
        return execution

    async def list_executions(
        self,
        procedure_id: uuid.UUID,
        status: str | None = None,
        limit: int = 10,
    ) -> list[ProcedureExecution]:
        query = select(ProcedureExecution).where(ProcedureExecution.procedure_id == procedure_id)
        if status:
            query = query.where(ProcedureExecution.status == status)
        query = query.order_by(ProcedureExecution.created_at.desc()).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars())

    async def update_execution(
        self,
        execution: ProcedureExecution,
        **kwargs: object,
    ) -> None:
        for key, value in kwargs.items():
            setattr(execution, key, value)
        await self.db.flush()
