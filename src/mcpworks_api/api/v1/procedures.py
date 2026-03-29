"""REST API endpoints for procedure management."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.core.database import get_db
from mcpworks_api.core.exceptions import ConflictError, NotFoundError
from mcpworks_api.dependencies import get_current_account, get_current_user, require_scope
from mcpworks_api.models.account import Account
from mcpworks_api.models.user import User
from mcpworks_api.schemas.procedure import (
    CreateProcedureRequest,
    ProcedureExecutionListResponse,
    ProcedureExecutionResponse,
    ProcedureListResponse,
    ProcedureResponse,
    ProcedureStepResponse,
)
from mcpworks_api.services.procedure_service import ProcedureService

router = APIRouter(prefix="/procedures", tags=["procedures"])


def _to_response(procedure, service_name: str) -> ProcedureResponse:
    version = procedure.get_active_version_obj()
    steps = []
    if version:
        for s in version.steps:
            steps.append(
                ProcedureStepResponse(
                    step_number=s["step_number"],
                    name=s["name"],
                    function_ref=s["function_ref"],
                    instructions=s["instructions"],
                    failure_policy=s.get("failure_policy", "required"),
                    max_retries=s.get("max_retries", 1),
                    validation=s.get("validation"),
                )
            )
    return ProcedureResponse(
        id=procedure.id,
        name=procedure.name,
        service_name=service_name,
        description=procedure.description,
        active_version=procedure.active_version,
        steps=steps,
        created_at=procedure.created_at,
        updated_at=procedure.updated_at,
    )


@router.post(
    "",
    response_model=ProcedureResponse,
    status_code=201,
    dependencies=[Depends(require_scope("write"))],
)
async def create_procedure(
    body: CreateProcedureRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),  # noqa: ARG001
    account: Account = Depends(get_current_account),
) -> ProcedureResponse:
    from sqlalchemy import select

    from mcpworks_api.models.namespace import Namespace

    ns_result = await db.execute(
        select(Namespace).where(Namespace.account_id == account.id).limit(1)
    )
    namespace = ns_result.scalar_one_or_none()
    if not namespace:
        raise HTTPException(status_code=404, detail="No namespace found")

    svc = ProcedureService(db)
    try:
        steps_dicts = [s.model_dump() for s in body.steps]
        procedure = await svc.create_procedure(
            namespace_id=namespace.id,
            service_name=body.service,
            name=body.name,
            steps=steps_dicts,
            description=body.description,
        )
        await db.commit()
        await db.refresh(procedure, ["versions"])
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return _to_response(procedure, body.service)


@router.get(
    "",
    response_model=ProcedureListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_procedures(
    service: str,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),
) -> ProcedureListResponse:
    from sqlalchemy import select

    from mcpworks_api.models.namespace import Namespace

    ns_result = await db.execute(
        select(Namespace).where(Namespace.account_id == account.id).limit(1)
    )
    namespace = ns_result.scalar_one_or_none()
    if not namespace:
        raise HTTPException(status_code=404, detail="No namespace found")

    svc = ProcedureService(db)
    try:
        procedures = await svc.list_procedures(namespace.id, service)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ProcedureListResponse(
        procedures=[_to_response(p, service) for p in procedures],
        total=len(procedures),
    )


@router.get(
    "/{procedure_id}",
    response_model=ProcedureExecutionListResponse,
    dependencies=[Depends(require_scope("read"))],
)
async def list_executions(
    procedure_id: uuid.UUID,
    status: str | None = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
    account: Account = Depends(get_current_account),  # noqa: ARG001
) -> ProcedureExecutionListResponse:
    svc = ProcedureService(db)
    executions = await svc.list_executions(procedure_id, status=status, limit=limit)
    return ProcedureExecutionListResponse(
        executions=[ProcedureExecutionResponse.model_validate(e) for e in executions],
        total=len(executions),
    )
