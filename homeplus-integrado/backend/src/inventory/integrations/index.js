'use strict';
const { resolveCapabilities, hasCapability } = require('../../lib/plannerCapabilities');
async function status(context){
  let planner=false;let finance=false;
  try{planner=hasCapability(resolveCapabilities({role:context.role,membershipStatus:context.membershipStatus,household:context.household}),'task.create_household');}catch{/* unavailable capability remains false */}
  try{finance=Boolean(context.personId&&context.householdId&&context.membership?.status==='active');}catch{/* unavailable context remains false */}
  return {planner:{can_create_household_task:planner},finance:{can_register_household_expense:finance}};
}
module.exports={status};


