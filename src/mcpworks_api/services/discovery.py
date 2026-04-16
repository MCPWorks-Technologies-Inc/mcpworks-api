"""Discovery service — generates .well-known/mcp.json server cards."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mcpworks_api.config import get_settings
from mcpworks_api.models.function import Function
from mcpworks_api.models.function_version import FunctionVersion
from mcpworks_api.models.namespace import Namespace
from mcpworks_api.models.namespace_service import NamespaceService
from mcpworks_api.schemas.discovery import (
    EndpointsInfo,
    NamespaceEntry,
    NamespaceServerCard,
    PlatformServerCard,
    ToolSummary,
)


class DiscoveryService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()
        self.domain = self.settings.base_domain

    async def get_namespace_card(self, namespace_name: str) -> NamespaceServerCard | None:
        result = await self.db.execute(
            select(Namespace).where(
                Namespace.name == namespace_name, Namespace.deleted_at.is_(None)
            )
        )
        namespace = result.scalar_one_or_none()
        if not namespace:
            return None

        svc_count_result = await self.db.execute(
            select(func.count(NamespaceService.id)).where(
                NamespaceService.namespace_id == namespace.id
            )
        )
        service_count = svc_count_result.scalar() or 0

        total_result = await self.db.execute(
            select(func.count(Function.id))
            .join(NamespaceService, Function.service_id == NamespaceService.id)
            .where(
                NamespaceService.namespace_id == namespace.id,
                Function.deleted_at.is_(None),
            )
        )
        total_tool_count = total_result.scalar() or 0

        public_q = await self.db.execute(
            select(Function, FunctionVersion)
            .join(NamespaceService, Function.service_id == NamespaceService.id)
            .join(
                FunctionVersion,
                (FunctionVersion.function_id == Function.id)
                & (FunctionVersion.version == Function.active_version),
            )
            .where(
                NamespaceService.namespace_id == namespace.id,
                Function.public_safe.is_(True),
                Function.deleted_at.is_(None),
            )
        )
        public_rows = public_q.all()

        tools = [
            ToolSummary(
                name=f.name,
                description=f.description,
                input_schema=v.input_schema,
            )
            for f, v in public_rows
        ]

        return NamespaceServerCard(
            name=namespace.name,
            description=namespace.description,
            endpoints=EndpointsInfo(
                create=f"https://{namespace.name}.create.{self.domain}/mcp",
                run=f"https://{namespace.name}.run.{self.domain}/mcp",
            ),
            tools=tools,
            private_tool_count=total_tool_count - len(tools),
            service_count=service_count,
            total_tool_count=total_tool_count,
        )

    async def get_platform_card(self) -> PlatformServerCard:
        result = await self.db.execute(
            select(Namespace)
            .where(Namespace.discoverable.is_(True), Namespace.deleted_at.is_(None))
            .order_by(Namespace.name)
        )
        namespaces = result.scalars().all()

        entries = []
        for ns in namespaces:
            fn_count_result = await self.db.execute(
                select(func.count(Function.id))
                .join(NamespaceService, Function.service_id == NamespaceService.id)
                .where(
                    NamespaceService.namespace_id == ns.id,
                    Function.deleted_at.is_(None),
                )
            )
            tool_count = fn_count_result.scalar() or 0

            entries.append(
                NamespaceEntry(
                    name=ns.name,
                    description=ns.description,
                    server_card_url=f"https://{ns.name}.create.{self.domain}/.well-known/mcp.json",
                    tool_count=tool_count,
                )
            )

        return PlatformServerCard(namespaces=entries)
