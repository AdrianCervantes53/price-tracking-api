from app.models.user import User


class UserRepository:
    async def get_by_email(self, email: str) -> User | None:
        return await User.find_one(User.email == email)

    async def create(self, email: str, hashed_password: str) -> User:
        user = User(email=email, hashed_password=hashed_password)
        await user.insert()
        return user
