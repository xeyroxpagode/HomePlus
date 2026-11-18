const express = require('express')
const authFinalMiddleware = require('../middleware/authFinalMiddleware')
const controller = require('../controllers/hplus.controller')

const router = express.Router()
router.use(authFinalMiddleware)
router.get('/summary', controller.getSummary)
router.get('/ledger', controller.listHistory)
module.exports = router
