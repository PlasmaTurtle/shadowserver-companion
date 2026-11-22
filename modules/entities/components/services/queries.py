"""Entity views combine profile and contact readiness in one read snapshot."""

from ..contact_outcomes import complete_entity_details


def entity_view(workspace, repository, entity_id):
    """Read one consistent entity projection without reserving a writer.

    The caller supplies the workspace connection boundary and entity repository.
    No case workflow, command service or application facade is needed here.
    """
    with workspace.read_snapshot() as db:
        entity = repository.lead(entity_id, db)
        if entity:
            from modules.investigations.components.website_evidence import projection

            entity["website"] = projection(db, entity_id, root_domain=entity["domain"])
            entity["entity_review"] = complete_entity_details(
                workspace, entity, entity["entity_review"], entity["entity_profile"], db
            )
        return entity
