from passlib.context import CryptContext

pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

hashed = pwd.hash("hhola13")
print(hashed)
