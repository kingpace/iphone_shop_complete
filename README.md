# NOVA Phones — Flask iPhone Shop

A standalone demo storefront with database-backed products, users, admin tools, cart, search, and filters. **No checkout or payments are enabled.**

## Set up (Windows PowerShell)

1. Open this folder in VS Code.
2. Create and activate a virtual environment:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. Install packages:

   ```powershell
   pip install -r requirements.txt
   ```

4. Set environment variables for your terminal session (choose your own values):

   ```powershell
   $env:SECRET_KEY = 'replace-this-with-a-long-random-secret'
   $env:ADMIN_EMAIL = 'you@example.com'
   $env:ADMIN_PASSWORD = 'replace-this-with-a-strong-12-character-password'
   ```

5. Create the database and admin account:

   ```powershell
   flask --app app init-db
   flask --app app create-admin
   ```

6. Start the development server:

   ```powershell
   flask --app app run --debug
   ```

7. Visit http://127.0.0.1:5000, sign in as admin, and add products.

## Notes

- This is a **separate project**. Do not copy its database over your existing phone shop database.
- Product images use direct image URLs entered by admins. Empty URLs show a placeholder.
- The site uses CSRF tokens for state-changing forms, session authentication, hashed passwords, ownership checks, and stock limits.
- For real production use: use HTTPS, production WSGI hosting, stronger input validation, rate limiting, a migration tool, proper image uploads and additional security review.
- `db.create_all()` only creates missing tables; it does not migrate existing table columns.
- The development-only fallback SECRET_KEY must be replaced before deployment.
- Prices use Decimal-compatible Numeric columns; all example price ranges are in GBP.
