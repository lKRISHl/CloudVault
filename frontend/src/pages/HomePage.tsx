import { HealthStatus } from '../components/ui/HealthStatus';
import { useAuth } from '../auth/AuthContext';

export function HomePage() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center p-4">
      <div className="max-w-3xl w-full flex flex-col items-center space-y-12">
        <div className="text-center space-y-4">
          <h1 className="text-6xl font-extrabold tracking-tight text-gray-900">
            Cloud<span className="text-blue-600">Vault</span>
          </h1>
          <p className="text-xl text-gray-500 font-light tracking-wide">
            AI-Native Cloud File Storage
          </p>
          {user && (
            <p className="text-sm text-gray-600">
              Signed in as <span className="font-medium">{user.full_name}</span> · {user.tenant.name}
            </p>
          )}
        </div>

        <div className="w-full max-w-md space-y-4">
          <HealthStatus />
          <button
            type="button"
            onClick={() => void logout()}
            className="w-full border border-gray-200 bg-white rounded-lg py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            Sign out
          </button>
        </div>
      </div>
    </div>
  );
}
