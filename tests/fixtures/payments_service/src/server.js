const express = require('express')
const Stripe = require('stripe')

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY)
const app = express()

app.post('/charge', async (req, res) => {
  const intent = await stripe.paymentIntents.create({
    amount: req.body.amount,
    currency: 'usd',
    payment_method: req.body.payment_method_id,
  })
  res.json({ id: intent.id })
})

app.listen(3000)
