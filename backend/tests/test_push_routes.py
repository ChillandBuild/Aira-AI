def test_push_public_key_is_on_public_router_only():
    """The VAPID public key is safe to expose and must not require auth."""
    from app.routes import push

    public_paths = [r.path for r in push.public_router.routes]
    auth_paths = [r.path for r in push.router.routes]

    assert "/public-key" in public_paths
    assert "/public-key" not in auth_paths


def test_push_subscription_routes_stay_auth_gated():
    """Subscription management stores user data and must remain auth-gated."""
    from app.routes import push

    public_paths = [r.path for r in push.public_router.routes]
    auth_paths = [r.path for r in push.router.routes]

    assert "/status" in auth_paths
    assert "/subscriptions" in auth_paths
    assert "/status" not in public_paths
    assert "/subscriptions" not in public_paths
