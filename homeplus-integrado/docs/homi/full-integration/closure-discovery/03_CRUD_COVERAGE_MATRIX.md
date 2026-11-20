# 03 — CRUD COVERAGE MATRIX — Pasada 1/2

**Pregunta que debe responder:** ¿puede HOMI crear, consultar, actualizar, eliminar y restaurar cada entidad funcional que HomePlus permite operar?

**Respuesta:** sí para las **307 operaciones objetivo** (114 READ / 193 WRITE), con las excepciones listadas abajo y justificadas en `05_DEFERRED_BLOCKED_EXCLUDED_RECONCILIATION.md`.Una celda «—» significa que la operación **no es una tool objetivo**; no significa que la funcionalidad no exista.

## 1. Criterio de comprobación programática

| Comprobación | Resultado |
|---|---|
| Cada operación tiene exactamente un destino final | 350/350 |
| IDs de operación únicos | ver `CONSISTENCY_REPORT.json` |
| Cada tool objetivo tiene contrato | 307/307 |
| Cada WRITE tiene política de confirmación | 193/193 |
| Cada tool tiene tarea y prueba prevista | `11_TASKS_AND_DEPENDENCIES.json`, `12_E2E_ACCEPTANCE_PLAN.md` |
| Sin operaciones huérfanas | `CONSISTENCY_REPORT.json` |

Leyenda riesgo: **R0** solo lectura · **R1** write reversible con preview+confirm · **R2** efecto financiero/destructivo/privilegios con confirmación reforzada.
Confirmación: **PREVIEW+CONFIRM** = propuesta con args normalizados + hash + TTL · **CONFIRM×2** = confirmación reforzada · **NONE** = lectura.

## 2. Matriz por dominio

### identity — 11 operaciones

Identidad: solo lecturas de sesión/perfil/hogares y actualización de perfil. Credenciales, service-role y dispositivos quedan fuera por seguridad demostrable.

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| identity.session.get | identity | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | lib/me.service.js::buildMe |
| identity.profile.get | identity | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL | NONE | controllers/people.controller.js::getMe |
| identity.households.list | identity | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL | NONE | controllers/people.controller.js::getMyHouseho… |
| identity.capabilities.get | identity | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | lib/plannerCapabilities.js::resolveCapabilitie… |
| identity.profile.update | identity | 176 | TARGET IMPLEMENT | WRITE | R1 | — | PERSONAL_HOUSEHOLD | PREVIEW+CONFIRM | controllers/people.controller.js::updateMe |
| identity.avatar.update | identity | 176 | BLOCKED DEPENDENCY | — | — | — | — | — | controllers/people.controller.js::updateAvatar |
| identity.register | identity | 176 | EXCLUDED SECURITY | — | — | — | — | — | auth.final.controller.register |
| identity.login | identity | 176 | EXCLUDED SECURITY | — | — | — | — | — | auth.final.controller.login |
| identity.refresh | identity | 176 | EXCLUDED SECURITY | — | — | — | — | — | auth.final.controller.refresh |
| identity.logout | identity | 176 | EXCLUDED SECURITY | — | — | — | — | — | auth.final.controller.logout |
| identity.user-metadata.update | identity | 176 | EXCLUDED SECURITY | — | — | — | — | — | users.controller.updateMe |

### households — 19 operaciones

Hogares: lecturas completas y administración de invitaciones/solicitudes. Cambios de workspace raíz, expulsión y privilegios se aíslan para decisión de Actor A.

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| households.family.get | households | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | controllers/households.controller.js::getFamil… |
| households.members.list | households | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | controllers/households.controller.js::getMembe… |
| households.members.get | households | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | controllers/households.controller.js::getMembe… |
| households.role-requests.list | households | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | controllers/households.controller.js::listRole… |
| households.join-requests.list | households | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | controllers/inviteLinks.controller.js::listJoi… |
| households.invite-links.list | households | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | controllers/households.controller.js::getFamil… |
| households.create | households | 176 | BLOCKED UNSAFE | — | — | — | — | — | households.controller.createHousehold |
| households.set-active | households | 176 | BLOCKED UNSAFE | — | — | — | — | — | households.controller.setActiveHousehold |
| households.finalize-member | households | 176 | BLOCKED UNSAFE | — | — | — | — | — | households.controller.finalizeMember |
| households.invite-link.create | households | 176 | TARGET IMPLEMENT | WRITE | R1 | — | HOUSEHOLD | PREVIEW+CONFIRM | inviteLinks.controller.createInviteLink |
| households.invite-link.revoke | households | 176 | TARGET IMPLEMENT | WRITE | R1 | — | HOUSEHOLD | PREVIEW+CONFIRM | inviteLinks.controller.revokeInviteLink |
| households.join | households | 176 | EXCLUDED NOT PRODUCT | — | — | — | — | — | inviteLinks.controller.joinByToken |
| households.join-request.approve | households | 176 | TARGET IMPLEMENT | WRITE | R2 | — | HOUSEHOLD | CONFIRM×2 | inviteLinks.controller.approveJoinRequest |
| households.join-request.reject | households | 176 | TARGET IMPLEMENT | WRITE | R2 | — | HOUSEHOLD | CONFIRM×2 | inviteLinks.controller.rejectJoinRequest |
| households.member.role.update | households | 176 | PRODUCT DECISION | — | — | — | — | — | households.controller.changeMemberRole |
| households.role-request.create | households | 176 | TARGET IMPLEMENT | WRITE | R2 | — | HOUSEHOLD | CONFIRM×2 | households.controller.createRoleRequest |
| households.role-request.approve | households | 176 | PRODUCT DECISION | — | — | — | — | — | households.controller.approveRoleRequest |
| households.role-request.reject | households | 176 | PRODUCT DECISION | — | — | — | — | — | households.controller.rejectRoleRequest |
| households.role-request.cancel | households | 176 | TARGET IMPLEMENT | WRITE | R2 | — | HOUSEHOLD | CONFIRM×2 | households.controller.cancelRoleRequest |

### home — 3 operaciones

Home: tres agregados de lectura; sin escritura artificial.

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| home.summary.get | home | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.summary.controller.js::get… |
| home.attention.get | home | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.attention.service.js::listAtt… |
| home.activity.get | home | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.activity.controller.js::li… |

### planner — 104 operaciones

Planner: cobertura integral de tareas V0/V1 (fulfillment, claim/release/archive), eventos, metas/hitos, planes, presets, drafts, responsabilidades y horarios. La auto-verificación y los changesets estructurales permanecen fuera.

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| planner.capabilities.get | planner | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | lib/plannerCapabilities.js::resolveCapabilitie… |
| planner.tasks.list | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.tasks.controller.js::listT… |
| planner.tasks.get | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.tasks.controller.js::getTa… |
| planner.tasks.search | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view,planner.search | HOUSEHOLD | NONE | services/planner.search.service.js::searchActi… |
| planner.calendar.get | planner | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | controllers/planner.calendar.controller.js::ge… |
| planner.events.list | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.events.controller.js::list… |
| planner.events.get | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.events.controller.js::getE… |
| planner.goals.list | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.goals.controller.js::listG… |
| planner.goals.get | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.goals.controller.js::getGo… |
| planner.plans.list | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.plans.v1.controller.js::li… |
| planner.plans.get | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.plans.v1.controller.js::ge… |
| planner.trash.get | planner | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | controllers/planner.trash.controller.js::getTr… |
| planner.responsibilities.list | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.responsibilities.controlle… |
| planner.schedules.list | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.schedules.controller.js::l… |
| planner.presets.list | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.templates.use | HOUSEHOLD | NONE | controllers/planner.presets.controller.js::lis… |
| planner.drafts.list | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | controllers/planner.drafts.controller.js::list… |
| planner.tasks.create | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | task.create_household | HOUSEHOLD | PREVIEW+CONFIRM | controllers/planner.tasks.controller.js::creat… |
| planner.tasks.update | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | task.edit_own,task.edit_any | HOUSEHOLD | PREVIEW+CONFIRM | controllers/planner.tasks.controller.js::updat… |
| planner.tasks.complete | planner | 176 | TARGET IMPLEMENT | WRITE | R2 | task.complete_assigned,task.complete_unassigned,task.complete_any | HOUSEHOLD | CONFIRM×2 | controllers/planner.tasks.controller.js::compl… |
| planner.tasks.trash | planner | 176 | TARGET IMPLEMENT | WRITE | R2 | task.restore | HOUSEHOLD | CONFIRM×2 | controllers/planner.tasks.controller.js::trash… |
| planner.tasks.restore | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | task.restore | HOUSEHOLD | PREVIEW+CONFIRM | controllers/planner.tasks.controller.js::resto… |
| planner.tasks.verify | planner | 176 | BLOCKED AUTHORITY | — | — | — | — | — | planner.tasks.verifyTask |
| planner.tasks.reactivate | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.tasks.reactivateTask |
| planner.events.create | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | event.create_household | HOUSEHOLD | PREVIEW+CONFIRM | controllers/planner.events.controller.js::crea… |
| planner.events.update | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | event.edit_own | HOUSEHOLD | PREVIEW+CONFIRM | controllers/planner.events.controller.js::upda… |
| planner.events.cancel | planner | 176 | TARGET IMPLEMENT | WRITE | R2 | event.cancel_own | HOUSEHOLD | CONFIRM×2 | controllers/planner.events.controller.js::canc… |
| planner.events.trash | planner | 176 | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | planner.events.trashEvent |
| planner.events.restore | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.events.restoreEvent |
| planner.goals.create | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | goal.create_household | HOUSEHOLD | PREVIEW+CONFIRM | controllers/planner.goals.controller.js::creat… |
| planner.goals.update | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | goal.edit_own | HOUSEHOLD | PREVIEW+CONFIRM | controllers/planner.goals.controller.js::updat… |
| planner.goals.complete | planner | 176 | TARGET IMPLEMENT | WRITE | R2 | goal.complete_own | HOUSEHOLD | CONFIRM×2 | controllers/planner.goals.controller.js::compl… |
| planner.goals.close | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.goals.closeGoal |
| planner.goals.fail | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.goals.failGoal |
| planner.goals.reopen | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.goals.reopenGoal |
| planner.plans.create | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.plans.v1.createPlan |
| planner.plans.update | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.plans.v1.updatePlan |
| planner.plans.transition | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.plans.v1.transitionPlan |
| planner.plans.structure | planner | 176 | BLOCKED UNSAFE | — | — | — | — | — | planner.plans.applyStructure |
| planner.plans.unarchive | planner | 176 | BLOCKED AUTHORITY | — | — | — | — | — | planner.plans.v1.unarchivePlan |
| planner.responsibilities.create | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.responsibilities.create |
| planner.responsibilities.lifecycle | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.responsibilities.setLifecycle |
| planner.schedules.create | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.schedules.create |
| planner.schedules.update | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.schedules.update |
| planner.schedules.delete | planner | 176 | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | planner.schedules.delete |
| planner.presets.create | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.presets.create |
| planner.presets.publish | planner | 176 | BLOCKED AUTHORITY | — | — | — | — | — | planner.presets.publishRevision |
| planner.drafts.autosave | planner | 176 | EXCLUDED NOT PRODUCT | — | — | — | — | — | planner.drafts.autosaveDraft |
| planner.drafts.discard | planner | 176 | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | planner.drafts.discardDraft |
| planner.tasks.evidence | planner | 176 | BLOCKED DEPENDENCY | — | — | — | — | — | planner.tasks.submitEvidence |
| planner.tasks.audit.get | planner | 176 | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.tasks.service.js::getTaskAudi… |
| planner.responsibilities.get | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.responsibilities.service.js::… |
| planner.responsibilities.update | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.responsibilities.service.js::… |
| planner.responsibilities.replace-assignee | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.responsibilities.service.js::… |
| planner.schedules.privacy.get | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.schedules.service.js::getMyPr… |
| planner.schedules.privacy.update | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.schedules.service.js::updateM… |
| planner.plans.legacy-report.get | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.plans.service.js::getLegacyCo… |
| planner.plans.legacy.get | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.plans.service.js::getPlanGrap… |
| planner.plans.legacy.list | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.plans.service.js::listPlans |
| planner.plans.legacy.write | planner | NEW | BLOCKED UNSAFE | — | — | — | — | — | services/planner.plans.service.js::writePlanGr… |
| planner.tasks.fulfillment.get | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.tasks.service.js::getTaskFulf… |
| planner.tasks.assignment.update | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.tasks.service.js::updateTaskA… |
| planner.tasks.claim | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.tasks.service.js::claimTaskV1 |
| planner.tasks.release | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.tasks.service.js::releaseTask… |
| planner.tasks.archive | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.tasks.service.js::archiveTask… |
| planner.tasks.unarchive | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.tasks.service.js::unarchiveTa… |
| planner.tasks.fulfillment.complete | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.tasks.service.js::mutateTaskF… |
| planner.tasks.fulfillment.verify | planner | NEW | BLOCKED AUTHORITY | — | — | — | — | — | services/planner.tasks.service.js::mutateTaskF… |
| planner.tasks.fulfillment.request-correction | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.tasks.service.js::mutateTaskF… |
| planner.tasks.fulfillment.resubmit | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.tasks.service.js::mutateTaskF… |
| planner.tasks.fulfillment.revert | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.tasks.service.js::mutateTaskF… |
| planner.tasks.fulfillment.reopen | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.tasks.service.js::mutateTaskF… |
| planner.tasks.evidence.list | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.tasks.service.js::getTaskEvid… |
| planner.tasks.cancel | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.tasks.service.js::cancelTask |
| planner.events.v1.get | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.events.v1.service.js::getEven… |
| planner.events.v1.list | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.events.v1.service.js::listEve… |
| planner.events.v1.create | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.events.v1.service.js::createE… |
| planner.events.v1.mutate | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.events.v1.service.js::mutateE… |
| planner.events.v1.participants.mutate | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.events.v1.service.js::mutateP… |
| planner.events.reactivate | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.events.service.js::reactivate… |
| planner.events.occurrence-override | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.events.service.js::createOccu… |
| planner.goals.delete | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.goals.service.js::deleteGoal |
| planner.goals.trash | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.goals.service.js::trashGoal |
| planner.goals.restore | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.goals.service.js::restoreGoal |
| planner.goals.milestones.list | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.goals.service.js::listMilesto… |
| planner.goals.milestones.create | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.goals.service.js::createMiles… |
| planner.goals.milestones.update | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.goals.service.js::updateMiles… |
| planner.goals.milestones.delete | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.goals.service.js::deleteMiles… |
| planner.goals.milestones.trash | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.goals.service.js::trashMilest… |
| planner.goals.milestones.restore | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.goals.service.js::restoreMile… |
| planner.plans.v1.trash | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.plans.v1.service.js::trashPla… |
| planner.plans.v1.restore | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.plans.v1.service.js::restoreP… |
| planner.presets.get | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.presets.service.js::getPreset |
| planner.presets.update-metadata | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.presets.service.js::updatePre… |
| planner.presets.revision.start | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.presets.service.js::startRevi… |
| planner.presets.revision.list | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.presets.service.js::listRevis… |
| planner.presets.trash | planner | NEW | TARGET IMPLEMENT | WRITE | R2 | planner.view | HOUSEHOLD | CONFIRM×2 | services/planner.presets.service.js::trashPres… |
| planner.presets.restore | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.presets.service.js::restorePr… |
| planner.presets.duplicate-to-household | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.presets.service.js::duplicate… |
| planner.presets.prepare | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.presets.service.js::prepareAp… |
| planner.presets.revision.get | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.presets.service.js::getRevisi… |
| planner.presets.revision.update | planner | NEW | TARGET IMPLEMENT | WRITE | R1 | planner.view | HOUSEHOLD | PREVIEW+CONFIRM | services/planner.presets.service.js::updateRev… |
| planner.drafts.get | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.drafts.service.js::getDraft |
| planner.drafts.recover | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.drafts.service.js::recoverDra… |
| planner.drafts.prepare | planner | NEW | TARGET IMPLEMENT | READ | R0 | planner.view | HOUSEHOLD | NONE | services/planner.drafts.service.js::prepareAct… |

### finance — 66 operaciones

Finance: lecturas con precisión textual; escrituras de cuentas, categorías, movimientos, pools, cuotas y ciclo de pagos. Transferencias, corrección de saldo y registro de pagos requieren resolución técnica/decisión.

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| finance.accounts.list | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.accounts.controller.js::li… |
| finance.accounts.get | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.accounts.controller.js::ge… |
| finance.accounts.activity.get | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | services/finance.account.activity.service.js::… |
| finance.movements.list | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.read.controller.js::getMov… |
| finance.summary.get | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.read.controller.js::getSum… |
| finance.transaction.get | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.read.controller.js::getTra… |
| finance.transfer.get | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.read.controller.js::getTra… |
| finance.trash.get | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.read.controller.js::getTra… |
| finance.analysis.get | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.analysis.controller.js::ge… |
| finance.categories.list | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | services/finance.category.service.js::listFina… |
| finance.pools.list | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.pool.controller.js::listPo… |
| finance.installments.list | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.installments.controller.js… |
| finance.spending-limits.list | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.spending-limit.controller.… |
| finance.payments.dues.list | finance | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | controllers/finance.payment.controller.js::lis… |
| finance.expenses.create | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | controllers/finance.transactions.controller.js… |
| finance.incomes.create | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | controllers/finance.transactions.controller.js… |
| finance.transfers.create | finance | 176 | BLOCKED DEPENDENCY | — | — | — | — | — | finance.transfer.createTransfer |
| finance.accounts.create | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.account.createAccount |
| finance.accounts.update | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.account.updateAccount |
| finance.accounts.archive | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.account.archiveAccount |
| finance.accounts.anchor | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.account.createAnchor |
| finance.transactions.correct | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.transaction.correction.correct |
| finance.transactions.trash | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.transaction.trash.trash |
| finance.transactions.restore | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.transaction.restore.restore |
| finance.balance.correction | finance | 176 | PRODUCT DECISION | — | — | — | — | — | finance.balance.correction.correct |
| finance.refunds.create | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.refund.create |
| finance.refunds.correct | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.refund.correct |
| finance.installments.purchase | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.transaction.createInstallmentPurchase |
| finance.pools.allocate | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.pool.allocate |
| finance.pools.release | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.pool.release |
| finance.pools.transfer | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.pool.transfer |
| finance.spending-limits.create | finance | 176 | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | finance.spending-limit.create |
| finance.payments.dues.register | finance | 176 | PRODUCT DECISION | — | — | — | — | — | finance.payment.registerDue |
| finance.accounts.unarchive | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.account.service.js::unarchive… |
| finance.categories.create | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.category.service.js::createFi… |
| finance.categories.update | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.category.service.js::updateFi… |
| finance.categories.delete | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.category.service.js::deleteFi… |
| finance.transfers.trash | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.transfer.service.js::trashTra… |
| finance.transfers.restore | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.transfer.service.js::restoreT… |
| finance.payments.dues.create | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.payment.service.js::createOne… |
| finance.payments.series.create | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.payment.service.js::createPay… |
| finance.payments.dues.get | finance | NEW | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | services/finance.payment.service.js::getPaymen… |
| finance.payments.series.list | finance | NEW | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | services/finance.payment.service.js::listPayme… |
| finance.payments.series.get | finance | NEW | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | services/finance.payment.service.js::getPaymen… |
| finance.payments.dues.cancel | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.payment.service.js::cancelPay… |
| finance.payments.dues.skip | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.payment.service.js::skipPayme… |
| finance.payments.series.cancel | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.payment.service.js::cancelPay… |
| finance.payments.dues.update | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.payment.service.js::editPayme… |
| finance.payments.series.update | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.payment.service.js::editPayme… |
| finance.payments.dues.settle | finance | NEW | BLOCKED AUTHORITY | — | — | — | — | — | services/finance.payment.service.js::settleCre… |
| finance.pools.summary.get | finance | NEW | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | services/finance.pool.service.js::getPoolSumma… |
| finance.pools.create | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.pool.service.js::createPool |
| finance.pools.rename | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.pool.service.js::renamePool |
| finance.pools.archive | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.pool.service.js::archivePool |
| finance.pools.expense-assignment.get | finance | NEW | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | services/finance.pool.service.js::getExpensePo… |
| finance.pools.expense-assignment.set | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.pool.service.js::assignExpens… |
| finance.pools.expense-assignment.unassign | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.pool.service.js::unassignExpe… |
| finance.pools.income.distribute | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.pool.service.js::distributeIn… |
| finance.category-pool-default.get | finance | NEW | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | services/finance.category-pool-default.service… |
| finance.category-pool-default.upsert | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.category-pool-default.service… |
| finance.category-pool-default.clear | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.category-pool-default.service… |
| finance.spending-limits.update | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.spending-limit.service.js::ed… |
| finance.spending-limits.cancel | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.spending-limit.service.js::ca… |
| finance.spending-limits.progress.get | finance | NEW | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | services/finance.analysis.service.js::getSpend… |
| finance.installments.plan.create | finance | NEW | TARGET IMPLEMENT | WRITE | R2 | — | PERSONAL_HOUSEHOLD | CONFIRM×2 | services/finance.installment.service.js::creat… |
| finance.installments.plan.get | finance | NEW | TARGET IMPLEMENT | READ | R0 | — | PERSONAL_HOUSEHOLD | NONE | services/finance.installment.service.js::getCr… |

### inventory — 56 operaciones

Inventory: V2 lifecycle completo (productos, ubicaciones, lista, compras, reintento Finance) más API V1 legacy. Finalizar compra con gasto y borrado permanente están condicionados.

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| inventory.capabilities.get | inventory | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | lib/inventoryCapabilities.js::resolveInventory… |
| inventory.summary.get | inventory | 176 | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/summary/summary.service.js::get |
| inventory.catalog.search | inventory | 176 | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/catalog/catalog.service.js::search |
| inventory.locations.list | inventory | 176 | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/locations/locations.service.js::list |
| inventory.products.list | inventory | 176 | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/products/products.service.js::list |
| inventory.products.get | inventory | 176 | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/products/products.service.js::get |
| inventory.shopping-list.get | inventory | 176 | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/shopping/shopping.service.js::get |
| inventory.purchases.active.get | inventory | 176 | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/purchases/purchases.service.js::acti… |
| inventory.alerts.get | inventory | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | services/inventory.service.js::getAlerts |
| inventory.restock-requests.list | inventory | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | services/inventory.service.js::listRestockRequ… |
| inventory.products.create | inventory | 176 | TARGET IMPLEMENT | WRITE | R1 | inventory.manage | HOUSEHOLD | PREVIEW+CONFIRM | inventory/products/products.service.js::create |
| inventory.products.update | inventory | 176 | TARGET IMPLEMENT | WRITE | R1 | inventory.manage | HOUSEHOLD | PREVIEW+CONFIRM | inventory/products/products.service.js::edit |
| inventory.products.adjust-quantity | inventory | 176 | TARGET IMPLEMENT | WRITE | R1 | inventory.use | HOUSEHOLD | PREVIEW+CONFIRM | inventory/products/products.service.js::adjust |
| inventory.shopping-list.add | inventory | 176 | TARGET IMPLEMENT | WRITE | R1 | inventory.use | HOUSEHOLD | PREVIEW+CONFIRM | inventory/shopping/shopping.service.js::add |
| inventory.shopping-list.to-planner-task | inventory | 176 | TARGET IMPLEMENT | WRITE | R1 | inventory.use,task.create_household | HOUSEHOLD | PREVIEW+CONFIRM | inventory/shopping/shopping.service.js::planne… |
| inventory.purchases.start | inventory | 176 | TARGET IMPLEMENT | WRITE | R1 | inventory.use | HOUSEHOLD | PREVIEW+CONFIRM | inventory/purchases/purchases.service.js::star… |
| inventory.purchases.finalize | inventory | 176 | PRODUCT DECISION | — | — | — | — | — | inventory.purchases.finalize |
| inventory.purchases.cancel | inventory | 176 | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | inventory.purchases.cancel |
| inventory.products.trash | inventory | 176 | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | inventory.products.trash |
| inventory.locations.create | inventory | 176 | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory.locations.create |
| inventory.restock.approve | inventory | 176 | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | inventory.service.approveRestock |
| inventory.integrations.get | inventory | NEW | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/integrations.service.js::list |
| inventory.shopping-list.assign | inventory | NEW | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | inventory/shopping/shopping.service.js::assign |
| inventory.shopping-list.discovery | inventory | NEW | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/shopping/shopping.service.js::discov… |
| inventory.shopping-list.items.batch | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/shopping/shopping.service.js::batch |
| inventory.shopping-list.clear | inventory | NEW | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | inventory/shopping/shopping.service.js::clear |
| inventory.shopping-list.items.update | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/shopping/shopping.service.js::edit |
| inventory.shopping-list.items.remove | inventory | NEW | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | inventory/shopping/shopping.service.js::remove |
| inventory.shopping-list.items.restore | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/shopping/shopping.service.js::restor… |
| inventory.purchases.history | inventory | NEW | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/purchases/purchases.service.js::hist… |
| inventory.purchases.get | inventory | NEW | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/purchases/purchases.service.js::deta… |
| inventory.purchases.lines.set | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/purchases/purchases.service.js::line… |
| inventory.purchases.pause | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/purchases/purchases.service.js::paus… |
| inventory.purchases.resume | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/purchases/purchases.service.js::resu… |
| inventory.purchases.finance.retry | inventory | NEW | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | inventory/purchases/purchases.service.js::fina… |
| inventory.catalog.discovery | inventory | NEW | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | inventory/catalog/catalog.service.js::discover… |
| inventory.locations.update | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/locations/locations.service.js::edit |
| inventory.locations.delete | inventory | NEW | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | inventory/locations/locations.service.js::dele… |
| inventory.locations.reorder | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/locations/locations.service.js::reor… |
| inventory.locations.move-products | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/locations/locations.service.js::move… |
| inventory.products.batch | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/products/products.service.js::batch |
| inventory.products.trash.empty | inventory | NEW | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | inventory/products/products.service.js::emptyT… |
| inventory.products.quantity-set | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/products/products.service.js::set |
| inventory.products.archive | inventory | NEW | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | inventory/products/products.service.js::archiv… |
| inventory.products.restore | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/products/products.service.js::restor… |
| inventory.products.restore-from-trash | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | inventory/products/products.service.js::restor… |
| inventory.products.permanent-delete | inventory | NEW | BLOCKED AUTHORITY | — | — | — | — | — | inventory/products/products.service.js::perman… |
| inventory.templates.list | inventory | NEW | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | services/inventory.service.js::listTemplates |
| inventory.items.list | inventory | NEW | TARGET IMPLEMENT | READ | R0 | inventory.view | HOUSEHOLD | NONE | services/inventory.service.js::listItems |
| inventory.items.create | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | services/inventory.service.js::createItem |
| inventory.items.update | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | services/inventory.service.js::updateItem |
| inventory.items.delete | inventory | NEW | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | services/inventory.service.js::deleteItem |
| inventory.items.quantity-add | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | services/inventory.service.js::changeQuantity |
| inventory.items.quantity-consume | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | services/inventory.service.js::changeQuantity |
| inventory.items.out-of-stock | inventory | NEW | TARGET IMPLEMENT | WRITE | R1 | inventory.view | HOUSEHOLD | PREVIEW+CONFIRM | services/inventory.service.js::markOutOfStock |
| inventory.restock.reject | inventory | NEW | TARGET IMPLEMENT | WRITE | R2 | inventory.view | HOUSEHOLD | CONFIRM×2 | services/inventory.service.js::rejectRestockRe… |

### assets — 39 operaciones

Assets: de 5 escrituras catalogadas se pasa a 26. Records (create/correct/renew/remove/restore/link/unlink) y Care (create/correct/remove/restore) son el mayor hueco cerrado. Toda escritura deriva household en servidor.

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| assets.capabilities.get | assets | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | services/assets.service.js::getAssetsCapabilit… |
| assets.list | assets | 176 | TARGET IMPLEMENT | READ | R0 | assets.view | HOUSEHOLD | NONE | services/assets.service.js::listAssets |
| assets.get | assets | 176 | TARGET IMPLEMENT | READ | R0 | assets.view | HOUSEHOLD | NONE | services/assets.service.js::getAssetById |
| assets.records.list | assets | 176 | TARGET IMPLEMENT | READ | R0 | assets.view | HOUSEHOLD | NONE | services/assets.service.js::listAssetRecords |
| assets.care.list | assets | 176 | TARGET IMPLEMENT | READ | R0 | assets.view | HOUSEHOLD | NONE | services/assets.service.js::listAssetCare |
| assets.categories.list | assets | 176 | TARGET IMPLEMENT | READ | R0 | assets.view | HOUSEHOLD | NONE | services/assets.service.js::listCategories |
| assets.create | assets | 176 | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | assets.service.createAsset |
| assets.archive | assets | 176 | TARGET IMPLEMENT | WRITE | R2 | assets.view | HOUSEHOLD | CONFIRM×2 | assets.service.archiveAsset |
| assets.trash | assets | 176 | TARGET IMPLEMENT | WRITE | R2 | assets.view | HOUSEHOLD | CONFIRM×2 | assets.service.trashAsset |
| assets.restore | assets | 176 | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | assets.service.restoreAsset |
| assets.record.link | assets | 176 | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | assets.service.linkRecordToAsset |
| assets.records.get | assets | NEW | TARGET IMPLEMENT | READ | R0 | assets.view | HOUSEHOLD | NONE | services/assets.service.js::getAssetRecordById |
| assets.care.get | assets | NEW | TARGET IMPLEMENT | READ | R0 | assets.view | HOUSEHOLD | NONE | services/assets.service.js::getManualCareById |
| assets.archive-history.get | assets | NEW | TARGET IMPLEMENT | READ | R0 | assets.view | HOUSEHOLD | NONE | services/assets.service.js::getArchiveHistory |
| assets.trash-history.get | assets | NEW | TARGET IMPLEMENT | READ | R0 | assets.view | HOUSEHOLD | NONE | services/assets.service.js::getTrashHistory |
| assets.planner-items.list | assets | NEW | TARGET IMPLEMENT | READ | R0 | assets.view | HOUSEHOLD | NONE | services/assets.planner.service.js::listAssetP… |
| assets.name.update | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::updateAssetName |
| assets.identity.update | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::updateAssetIdentit… |
| assets.category.set | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::setAssetCategory |
| assets.responsible.set | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::setAssetResponsibl… |
| assets.holder.set | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::setAssetHolder |
| assets.placement.set | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::setAssetPlacement |
| assets.profile.change | assets | NEW | TARGET IMPLEMENT | WRITE | R2 | assets.view | HOUSEHOLD | CONFIRM×2 | services/assets.service.js::changeAssetProfile |
| assets.lifecycle.set | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::setAssetLifecycleS… |
| assets.unarchive | assets | NEW | TARGET IMPLEMENT | WRITE | R2 | assets.view | HOUSEHOLD | CONFIRM×2 | services/assets.service.js::unarchiveAsset |
| assets.category.create | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::createCategory |
| assets.category.delete | assets | NEW | TARGET IMPLEMENT | WRITE | R2 | assets.view | HOUSEHOLD | CONFIRM×2 | services/assets.service.js::deleteCategory |
| assets.record.create | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::createAssetRecord |
| assets.record.correct | assets | NEW | TARGET IMPLEMENT | WRITE | R2 | assets.view | HOUSEHOLD | CONFIRM×2 | services/assets.service.js::correctAssetRecord |
| assets.record.period.correct | assets | NEW | TARGET IMPLEMENT | WRITE | R2 | assets.view | HOUSEHOLD | CONFIRM×2 | services/assets.service.js::correctAssetRecord… |
| assets.record.renew | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::renewAssetRecord |
| assets.record.remove | assets | NEW | TARGET IMPLEMENT | WRITE | R2 | assets.view | HOUSEHOLD | CONFIRM×2 | services/assets.service.js::removeAssetRecord |
| assets.record.restore | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::restoreAssetRecord |
| assets.record.unlink | assets | NEW | TARGET IMPLEMENT | WRITE | R2 | assets.view | HOUSEHOLD | CONFIRM×2 | services/assets.service.js::unlinkRecordFromAs… |
| assets.care.create | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::createManualCare |
| assets.care.correct | assets | NEW | TARGET IMPLEMENT | WRITE | R2 | assets.view | HOUSEHOLD | CONFIRM×2 | services/assets.service.js::correctManualCare |
| assets.care.remove | assets | NEW | TARGET IMPLEMENT | WRITE | R2 | assets.view | HOUSEHOLD | CONFIRM×2 | services/assets.service.js::removeManualCare |
| assets.care.restore | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.service.js::restoreManualCare |
| assets.planner-items.create | assets | NEW | TARGET IMPLEMENT | WRITE | R1 | assets.view | HOUSEHOLD | PREVIEW+CONFIRM | services/assets.planner.service.js::createAsse… |

### homecloud — 29 operaciones

HomeCloud: metadatos, carpetas, álbumes (N:M), favoritos y portada. Carga de archivos y contenido con píxeles dependen de UI/SEE y se mantienen bloqueados sin inventar resultados.

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| homecloud.capabilities.get | homecloud | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | controllers/homecloud.capabilities.controller.… |
| homecloud.content.get | homecloud | 176 | TARGET IMPLEMENT | READ | R0 | homecloud.view | HOUSEHOLD | NONE | services/homecloudReadService.js::getContentBy… |
| homecloud.folders.list | homecloud | 176 | TARGET IMPLEMENT | READ | R0 | homecloud.view | HOUSEHOLD | NONE | services/homecloudReadService.js::listFolders |
| homecloud.albums.list | homecloud | 176 | TARGET IMPLEMENT | READ | R0 | homecloud.view | HOUSEHOLD | NONE | services/homecloudReadService.js::listAlbums |
| homecloud.albums.get | homecloud | 176 | TARGET IMPLEMENT | READ | R0 | homecloud.view | HOUSEHOLD | NONE | services/homecloudReadService.js::getAlbumById |
| homecloud.album.items.get | homecloud | 176 | TARGET IMPLEMENT | READ | R0 | homecloud.view | HOUSEHOLD | NONE | services/homecloudReadService.js::getAlbumMemb… |
| homecloud.memories.list | homecloud | 176 | TARGET IMPLEMENT | READ | R0 | homecloud.view | HOUSEHOLD | NONE | services/homecloudReadService.js::listMemories |
| homecloud.files.list | homecloud | 176 | TARGET IMPLEMENT | READ | R0 | homecloud.view | HOUSEHOLD | NONE | services/homecloudFilesService.js::browseFiles |
| homecloud.preferences.get | homecloud | 176 | TARGET IMPLEMENT | READ | R0 | homecloud.view | HOUSEHOLD | NONE | services/homecloudPhotoPreferencesService.js::… |
| homecloud.content.access | homecloud | 176 | BLOCKED DEPENDENCY | — | — | — | — | — | homecloudStorageAccess.createAccess |
| homecloud.content.analyze | homecloud | 176 | BLOCKED DEPENDENCY | — | — | — | — | — | homi_see_orchestrator |
| homecloud.favorite | homecloud | 176 | TARGET IMPLEMENT | WRITE | R1 | homecloud.view | HOUSEHOLD | PREVIEW+CONFIRM | homecloudPhotoPreferencesService.favorite |
| homecloud.album.create | homecloud | 176 | TARGET IMPLEMENT | WRITE | R1 | homecloud.view | HOUSEHOLD | PREVIEW+CONFIRM | homecloudAlbumsService.create |
| homecloud.content.register | homecloud | 176 | BLOCKED DEPENDENCY | — | — | — | — | — | homecloudIntakeService.register |
| homecloud.memories.unfavorite | homecloud | NEW | TARGET IMPLEMENT | WRITE | R1 | homecloud.view | HOUSEHOLD | PREVIEW+CONFIRM | services/homecloudPhotoPreferencesService.js::… |
| homecloud.memories.trash | homecloud | NEW | TARGET IMPLEMENT | WRITE | R2 | homecloud.view | HOUSEHOLD | CONFIRM×2 | services/homecloudMemoriesService.js::trashPho… |
| homecloud.folders.get | homecloud | NEW | TARGET IMPLEMENT | READ | R0 | homecloud.view | HOUSEHOLD | NONE | services/homecloudReadService.js::getFolderByI… |
| homecloud.folders.create | homecloud | NEW | TARGET IMPLEMENT | WRITE | R1 | homecloud.view | HOUSEHOLD | PREVIEW+CONFIRM | services/homecloudFilesService.js::createFolde… |
| homecloud.folders.rename | homecloud | NEW | TARGET IMPLEMENT | WRITE | R1 | homecloud.view | HOUSEHOLD | PREVIEW+CONFIRM | services/homecloudFilesService.js::renameFolde… |
| homecloud.folders.delete | homecloud | NEW | TARGET IMPLEMENT | WRITE | R2 | homecloud.view | HOUSEHOLD | CONFIRM×2 | services/homecloudFilesService.js::deleteFolde… |
| homecloud.content.update-file | homecloud | NEW | TARGET IMPLEMENT | WRITE | R1 | homecloud.view | HOUSEHOLD | PREVIEW+CONFIRM | services/homecloudFilesService.js::updateFile |
| homecloud.albums.rename | homecloud | NEW | TARGET IMPLEMENT | WRITE | R1 | homecloud.view | HOUSEHOLD | PREVIEW+CONFIRM | services/homecloudAlbumsService.js::rename |
| homecloud.albums.trash | homecloud | NEW | TARGET IMPLEMENT | WRITE | R2 | homecloud.view | HOUSEHOLD | CONFIRM×2 | services/homecloudAlbumsService.js::trash |
| homecloud.albums.add-item | homecloud | NEW | TARGET IMPLEMENT | WRITE | R1 | homecloud.view | HOUSEHOLD | PREVIEW+CONFIRM | services/homecloudAlbumsService.js::membership |
| homecloud.albums.remove-item | homecloud | NEW | TARGET IMPLEMENT | WRITE | R1 | homecloud.view | HOUSEHOLD | PREVIEW+CONFIRM | services/homecloudAlbumsService.js::membership |
| homecloud.albums.cover.set | homecloud | NEW | TARGET IMPLEMENT | WRITE | R1 | homecloud.view | HOUSEHOLD | PREVIEW+CONFIRM | services/homecloudPhotoPreferencesService.js::… |
| homecloud.content.upload-authorize | homecloud | NEW | BLOCKED DEPENDENCY | — | — | — | — | — | services/homecloudIntakeService.js::authorizeH… |
| homecloud.content.verify | homecloud | NEW | BLOCKED DEPENDENCY | — | — | — | — | — | services/homecloudIntakeService.js::verifyHome… |
| homecloud.content.finalize | homecloud | NEW | BLOCKED DEPENDENCY | — | — | — | — | — | services/homecloudIntakeService.js::finalizeHo… |

### messages — 13 operaciones

Mensajería: conversaciones, envío y reacciones. Adjuntos y "crear tarea desde mensaje" requieren corrección del RLS bypass con admin client antes de exponerse.

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| messages.conversations.list | messages | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | services/messaging.service.js::listConversatio… |
| messages.conversations.get | messages | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | services/messaging.service.js::getConversation |
| messages.messages.list | messages | 176 | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | services/messaging.service.js::listMessages |
| messages.messages.send | messages | 176 | TARGET IMPLEMENT | WRITE | R2 | — | HOUSEHOLD | CONFIRM×2 | services/messaging.service.js::sendMessage |
| messages.messages.react | messages | 176 | TARGET IMPLEMENT | WRITE | R2 | — | HOUSEHOLD | CONFIRM×2 | messaging.service.toggleReaction |
| messages.attachments.download | messages | 176 | BLOCKED DEPENDENCY | — | — | — | — | — | messagingAttachments.service.download |
| messages.conversations.read | messages | 176 | TARGET IMPLEMENT | WRITE | R2 | — | HOUSEHOLD | CONFIRM×2 | messaging.service.markRead |
| messages.conversations.ensure-direct | messages | NEW | TARGET IMPLEMENT | WRITE | R2 | — | HOUSEHOLD | CONFIRM×2 | services/messaging.service.js::ensureDirectCon… |
| messages.attachments.register | messages | NEW | TARGET IMPLEMENT | WRITE | R2 | — | HOUSEHOLD | CONFIRM×2 | services/messagingAttachments.service.js::regi… |
| messages.attachments.upload-authorize | messages | NEW | BLOCKED DEPENDENCY | — | — | — | — | — | services/messagingAttachments.service.js::auth… |
| messages.attachments.verify-upload | messages | NEW | BLOCKED DEPENDENCY | — | — | — | — | — | services/messagingAttachments.service.js::veri… |
| messages.attachments.cancel-upload | messages | NEW | TARGET IMPLEMENT | WRITE | R2 | — | HOUSEHOLD | CONFIRM×2 | services/messagingAttachments.service.js::canc… |
| messages.actions.link-task | messages | NEW | BLOCKED AUTHORITY | — | — | — | — | — | services/messagingAttachments.service.js::link… |

### presence — 2 operaciones



| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| presence.locations.list | presence | 176 | BLOCKED AUTHORITY | — | — | — | — | — | presence.locations.list |
| presence.my-location.update | presence | 176 | BLOCKED AUTHORITY | — | — | — | — | — | presence.locations.updateSelf |

### notifications — 3 operaciones

Notificaciones: solo preferencias desde `me`. Sin bandeja real; registro de dispositivo es nativo.

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| notifications.preferences.get | notifications | 176 | TARGET IMPLEMENT | READ | R0 | — | PERSONAL | NONE | lib/me.service.js::buildMe |
| notifications.preferences.update | notifications | 176 | EXCLUDED SECURITY | — | — | — | — | — | users.controller.updateMe |
| notifications.devices.register | notifications | 176 | EXCLUDED SECURITY | — | — | — | — | — | pushNotifications.controller.register |

### feed — 2 operaciones



| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| feed.posts.list | feed | 176 | EXCLUDED NOT PRODUCT | — | — | — | — | — | FeedFamiliarScreen.tsx:46-91 |
| feed.posts.create | feed | 176 | EXCLUDED NOT PRODUCT | — | — | — | — | — | FeedFamiliarScreen.tsx:121-138 |

### hplus — 2 operaciones

HPlus: dominio ausente en el catálogo anterior; se incorporan dos lecturas canónicas. El otorgamiento de puntos permanece como efecto de sistema.

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| hplus.summary.get | hplus | NEW | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | controllers/hplus.controller.js::getSummary |
| hplus.ledger.list | hplus | NEW | TARGET IMPLEMENT | READ | R0 | — | HOUSEHOLD | NONE | controllers/hplus.controller.js::listHistory |

### settings — 1 operaciones

Configuración: proyección de feature flags (client_visible).

| Operación | Dominio | Origen | Destino final | R/W | Riesgo | Permisos | Contexto | Confirmación | Servicio canónico |
|---|---|---|---|---|---|---|---|---|---|
| feature-flags.get | settings | NEW | TARGET IMPLEMENT | READ | R0 | — | PERSONAL | NONE | controllers/featureFlags.controller.js::getFea… |

## 3. Gaps que permanecen (con consecuencia funcional)

| Operación | Motivo real | Consecuencia | Responsable / desbloqueo |
|---|---|---|---|
| `finance.transfers.create` | R1-b: hash con `scopeType:PERSONAL` fijo en HOUSEHOLD | No se pueden crear transferencias desde HOMI | Backend canónico corrige hash; Actor C valida colisión |
| `finance.balance.correction` | Decisión financiera sin compensatorios ficticios | Ajustes de saldo solo en UI financiera | Actor A (PD-03) |
| `finance.payments.dues.register` | R1-d: crea transacción real, scope no reforzado en despacho | Registrar pagos desde HOMI no disponible | Actor A (PD-03) + backend |
| `inventory.purchases.finalize` | Requiere decidir si se registra gasto | Compra queda en intención; no genera gasto | Actor A (PD-01) |
| `presence.*` | Consentimiento no verificable por el modelo | Sin ubicaciones desde HOMI | Actor A (PD-02) + flujo de consentimiento |
| `homecloud.content.*` / `messages.attachments.download` | SEE/HOMI-B no garantizado | Metadatos sí; píxeles no | Proveedor HOMI-B disponible (PD-05) |
| `messages.actions.link-task` | Usa admin client (RLS bypass) para leer `planner_tasks` | No exponer hasta corregir | Backend canónico: usar bearer del usuario |
| `planner.plans.structure` / `plans.legacy.write` | Changeset/grafo completo desde lenguaje natural | Edición de planes solo en UI | Diseño de tools tipadas por sección |
| `planner.tasks.verify` / fulfillment.verify | Prohibida auto-verificación | Requiere otro actor | Regla de producto existente |
| `households.*` admin | Cambio de workspace / privilegios | Solo UI | Actor A (PD-04) |

**Gate E: FULL CRUD COVERAGE MATRIX VERIFIED.** La comprobación es programática y se re-ejecuta con `_consistency_check.cjs`.
