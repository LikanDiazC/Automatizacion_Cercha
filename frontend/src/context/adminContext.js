import { createContext } from 'react';

export const AdminContext = createContext({
  adminSession: { user: '', token: '' },
  isAdmin: false,
  openAdminDialog: () => {},
  closeAdminDialog: () => {},
  loginAdmin: () => {},
  logoutAdmin: () => {}
});
