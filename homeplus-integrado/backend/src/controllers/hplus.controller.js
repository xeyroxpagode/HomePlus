const { getPlannerContext } = require('../services/planner.context.service')
const hplus = require('../services/hplus.service')

const getSummary = async (req, res, next) => {
  try { res.json(await hplus.getSummary(await getPlannerContext(req))) } catch (error) { next(error) }
}
const listHistory = async (req, res, next) => {
  try { res.json(await hplus.listHistory(await getPlannerContext(req), req.query.limit)) } catch (error) { next(error) }
}
module.exports = { getSummary, listHistory }
